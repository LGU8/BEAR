# record/views_api.py
import os
import re
import uuid
import json
import tempfile
import math
import requests
from pathlib import Path
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.db import connection, transaction
from django.db.models import Max
from django.db.models.functions import Coalesce

from .services.storage.s3_client import upload_fileobj
from .services.storage.s3_paths import build_ocr_input_key, get_env_name


from .services.barcode.total import run_barcode_pipeline
from .services.barcode.mapping_code import (
    EnvNotSetError,
    UpstreamAPIError,
    get_nutrition_by_report_no,
)

from .models import FoodTb, CusFoodTh, CusFoodTs
from .utils_time import now14


# =========================
# 1) Common Normalizers / Helpers
# =========================
def _normalize_candidate(raw):
    """
    mapping_code.get_product_info_by_barcode() 결과(C005) → 프론트/commit 공통 규격으로 정규화
    """
    return {
        "candidate_id": raw.get("candidate_id", ""),
        "name": raw.get("product_name", ""),
        "brand": raw.get("manufacturer", ""),
        "flavor": raw.get("flavor", ""),
        "report_no": raw.get("report_no", ""),
        "kcal": None,
        "carb_g": None,
        "protein_g": None,
        "fat_g": None,
    }


def _normalize_rgs_dt_yyyymmdd(raw: str) -> str:
    # "2026-01-02" / "20260102" / "2026/01/02" 모두 -> "20260102"
    s = (raw or "").strip()
    s = "".join(ch for ch in s if ch.isdigit())
    return s


def _normalize_time_slot(raw: str) -> str:
    """
    들어오는 time_slot을 DB 표준값 'M'/'L'/'D'로 통일.
    허용 예:
    - 'M','L','D'
    - 'm','l','d'
    - 'breakfast','lunch','dinner'
    - '아침','점심','저녁'
    """
    s = (raw or "").strip()
    if not s:
        return ""

    s_low = s.lower()

    if s_low in ("m", "l", "d"):
        return s_low.upper()

    mapping = {
        "breakfast": "M",
        "lunch": "L",
        "dinner": "D",
        "아침": "M",
        "점심": "L",
        "저녁": "D",
    }
    return mapping.get(s_low, mapping.get(s, ""))


def _normalize_food_name(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _get_or_create_food_id_by_name(
    *,
    name: str,
    kcal: int,
    carb_g: int,
    protein_g: int,
    fat_g: int,
    mr_c: int,
    mr_p: int,
    mr_f: int,
    created_time: str | None = None,
    updated_time: str | None = None,
):
    """
    FOOD_TB에 같은 name이 있으면 해당 food_id 반환
    없으면 새 food_id 생성 + FOOD_TB insert
    """
    name_n = _normalize_food_name(name)
    if not name_n:
        raise ValueError("food name is empty")

    t_create = created_time or now14()
    t_update = updated_time or t_create

    with transaction.atomic():
        existing = FoodTb.objects.filter(name=name_n).order_by("food_id").first()
        if existing:
            return existing.food_id, False

        if len(name_n) >= 3:
            sim = (
                FoodTb.objects.filter(name__icontains=name_n)
                .order_by("food_id")
                .first()
            )
            if sim:
                return sim.food_id, False

        last_id = FoodTb.objects.aggregate(mx=Max("food_id"))["mx"] or 0
        new_id = int(last_id) + 1

        FoodTb.objects.create(
            created_time=t_create,
            updated_time=t_update,
            food_id=new_id,
            name=name_n,
            kcal=kcal,
            carb_g=carb_g,
            protein_g=protein_g,
            fat_g=fat_g,
            Macro_ratio_c=mr_c,
            Macro_ratio_p=mr_p,
            Macro_ratio_f=mr_f,
        )
        return new_id, True


def _get_or_create_food_seq_for_slot(
    *, cust_id: int, rgs_dt: str, time_slot: str
) -> int:
    """
    같은 cust_id + rgs_dt + time_slot이면 동일 seq를 재사용.
    없으면 cust_id 기준 MAX(seq)+1로 새로 발급.
    """
    existed = (
        CusFoodTh.objects.select_for_update()
        .filter(cust_id=cust_id, rgs_dt=rgs_dt, time_slot=time_slot)
        .order_by("-seq")
        .first()
    )
    if existed:
        return int(existed.seq)

    last_th = (
        CusFoodTh.objects.select_for_update()
        .filter(cust_id=cust_id)
        .order_by("-seq")
        .first()
    )
    return int((last_th.seq if last_th else 0) + 1)


def _derive_reco_target(rgs_dt: str, recorded_slot: str):
    """
    recorded_slot(실제 기록): CUS_FOOD_TH.time_slot
    reco_slot(추천 대상): MENU_RECOM_TH.rec_time_slot

    - M 기록 -> L 추천
    - L 기록 -> D 추천
    - D 기록 -> 다음날 M 추천

    반환: (reco_rgs_dt, reco_time_slot)
    """
    recorded_slot = (recorded_slot or "").strip().upper()
    rgs_dt = _normalize_rgs_dt_yyyymmdd(rgs_dt)

    if recorded_slot == "M":
        return rgs_dt, "L"
    if recorded_slot == "L":
        return rgs_dt, "D"
    if recorded_slot == "D":
        try:
            dt = datetime.strptime(rgs_dt, "%Y%m%d").date()
            dt2 = dt + timedelta(days=1)
            return dt2.strftime("%Y%m%d"), "M"
        except Exception:
            return rgs_dt, "M"

    return rgs_dt, ""


def _fetch_recent_food_names(cursor, cust_id, limit=10):
    """
    CUS_FOOD_TS -> FOOD_TB(name) 조인해서 최근 음식명 리스트 생성.
    - 최신순: rgs_dt desc, seq desc, food_seq asc
    """
    try:
        cursor.execute(
            f"""
            SELECT f.name
            FROM CUS_FOOD_TS s
            JOIN FOOD_TB f ON f.food_id = s.food_id
            WHERE s.cust_id = %s
            ORDER BY s.rgs_dt DESC, s.seq DESC, s.food_seq ASC
            LIMIT {int(limit)};
            """,
            [cust_id],
        )
        rows = cursor.fetchall() or []
        names = []
        for (nm,) in rows:
            nm = (nm or "").strip()
            if nm:
                names.append(nm)

        uniq = []
        seen = set()
        for n in names:
            if n not in seen:
                uniq.append(n)
                seen.add(n)
        return uniq[:limit]
    except Exception:
        return []


def _parse_body_json(request):
    """
    JSON body 안전 파서
    """
    try:
        return json.loads((request.body or b"{}").decode("utf-8") or "{}")
    except Exception:
        return {}


def to_int_trunc(v, default=0):
    """
    소수점 버림(int) 변환.
    - '12.9', 12.9, None, '' 등 안전 처리
    - 반올림 X, 그냥 버림 O
    """
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except (TypeError, ValueError):
        return default


def macro_ratio_10(carb_g, protein_g, fat_g):
    """
    - kcal 기여 기준 (탄4, 단4, 지9)
    - 결과는 (carb10, protein10, fat10)
    - 합이 반드시 10
    """
    carb_k = max(0, to_int_trunc(carb_g)) * 4
    prot_k = max(0, to_int_trunc(protein_g)) * 4
    fat_k = max(0, to_int_trunc(fat_g)) * 9

    total = carb_k + prot_k + fat_k
    if total <= 0:
        return 0, 0, 0

    raw = [carb_k / total * 10, prot_k / total * 10, fat_k / total * 10]
    base = [math.floor(x) for x in raw]
    remain = 10 - sum(base)

    frac = [(raw[i] - base[i], i) for i in range(3)]
    frac.sort(reverse=True)

    for i in range(remain):
        base[frac[i][1]] += 1

    return tuple(base)


def _nutr_payload(nutr_dict, source: str):
    if nutr_dict is None:
        return {
            "kcal": None,
            "carb_g": None,
            "protein_g": None,
            "fat_g": None,
            "nutr_source": source,
        }
    return {
        "kcal": nutr_dict.get("kcal"),
        "carb_g": nutr_dict.get("carb_g"),
        "protein_g": nutr_dict.get("protein_g"),
        "fat_g": nutr_dict.get("fat_g"),
        "nutr_source": source,
    }


# =========================
# 2) Barcode Scan / Draft / Commit
# =========================
@csrf_exempt
@require_POST
def api_barcode_scan(request):
    mode = request.POST.get("mode", "barcode")
    image = request.FILES.get("image")
    date = request.POST.get("date", "").strip()
    meal = request.POST.get("meal", "").strip()

    # ✅ [SCANDBG] 업로드 파일 디버그 로그 (image 받은 직후)
    f = request.FILES.get("image")
    print(
        "[SCANDBG] method=",
        request.method,
        "path=",
        request.path,
        "content_type=",
        request.content_type,
        "file=",
        (f.name if f else None),
        "size=",
        (f.size if f else None),
        "img_content_type=",
        (getattr(f, "content_type", None) if f else None),
        flush=True,
    )


    if not image:
        return JsonResponse(
            {"ok": False, "error": "IMAGE_REQUIRED", "message": "image is required  "},
            status=400,
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        for chunk in image.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        barcode, raw_candidates = run_barcode_pipeline(tmp_path)

        barcode = str(barcode).strip()
        raw_candidates = raw_candidates or []
        if isinstance(raw_candidates, dict):
            raw_candidates = [raw_candidates]

        if not barcode:
            return JsonResponse(
                {
                    "ok": False,
                    "reason": "SCAN_FAIL",
                    "barcode": "",
                    "message": "바코드를 인식하지 못했어요. 바코드를 네모칸 안에 맞추고 다시 시도해 주세요.",
                },
                status=400,
            )

    except EnvNotSetError as e:
        return JsonResponse(
            {"ok": False, "error": "ENV_NOT_SET", "message": str(e)}, status=500
        )
    except UpstreamAPIError as e:
        return JsonResponse(
            {
                "ok": False,
                "error": "UPSTREAM_API_ERROR",
                "message": str(e),
                "detail": getattr(e, "detail", None),
            },
            status=502,
        )
    except Exception as e:
        return JsonResponse(
            {"ok": False, "error": "SERVER_ERROR", "detail": str(e)}, status=500
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    candidates = [_normalize_candidate(x) for x in raw_candidates]
    candidates = [c for c in candidates if c.get("candidate_id")]

    if not candidates:
        return JsonResponse(
            {
                "ok": False,
                "reason": "NO_MATCH",
                "barcode": barcode,
                "message": "해당 바코드로 조회되는 제품이 없습니다. 검색으로 추가해 주세요.",
            },
            status=404,
        )

    # 영양 merge
    for c in candidates:

        c.update(_nutr_payload(None, "no_data"))

        report_no = (c.get("report_no") or "").strip()
        product_name = (c.get("name") or "").strip()
        if not report_no or not product_name:
            continue

        try:
            nutr = get_nutrition_by_report_no(report_no, product_name=product_name)

            if nutr is None:
                c.update(_nutr_payload(None, "no_data"))
            else:
                c.update(_nutr_payload(nutr, "api"))

        except UpstreamAPIError as e:
            if getattr(e, "detail", "") == "timeout":
                c.update(_nutr_payload(None, "timeout"))
            else:
                c.update(_nutr_payload(None, "error"))

        except Exception as e:
            # ✅ UpstreamAPIError로 감싸지지 않은 Timeout/네트워크 오류까지 여기서 흡수
            if isinstance(
                e, requests.exceptions.ReadTimeout
            ) or "Read timed out" in str(e):
                c.update(_nutr_payload(None, "timeout"))
            else:
                c.update(_nutr_payload(None, "error"))

    draft_id = uuid.uuid4().hex
    request.session[f"barcode_draft:{draft_id}"] = {
        "date": date,
        "meal": meal,
        "barcode": barcode,
        "mode": mode,
        "candidates": candidates,
    }
    request.session.modified = True

    slim = [
        {
            "candidate_id": c["candidate_id"],
            "name": c.get("name", ""),
            "brand": c.get("brand", ""),
            "flavor": c.get("flavor", ""),
            "kcal": c.get("kcal"),
            "carb_g": c.get("carb_g"),
            "protein_g": c.get("protein_g"),
            "fat_g": c.get("fat_g"),
            "nutr_source": c.get("nutr_source"),
        }
        for c in candidates
    ]

    return JsonResponse(
        {
            "ok": True,
            "draft_id": draft_id,
            "barcode": barcode,
            "date": date,
            "meal": meal,
            "mode": mode,
            "candidates": slim,
        },
        status=200,
    )


@require_GET
def api_barcode_draft(request):
    draft_id = request.GET.get("draft_id", "").strip()
    data = request.session.get(f"barcode_draft:{draft_id}")
    if not data:
        return JsonResponse(
            {"ok": False, "error": "DRAFT_NOT_FOUND", "message": "draft not found"},
            status=404,
        )

    candidates = data.get("candidates", [])
    slim = [
        {
            "candidate_id": c["candidate_id"],
            "name": c.get("name", ""),
            "brand": c.get("brand", ""),
            "flavor": c.get("flavor", ""),
            "kcal": c.get("kcal"),
            "carb_g": c.get("carb_g"),
            "protein_g": c.get("protein_g"),
            "fat_g": c.get("fat_g"),
        }
        for c in candidates
    ]

    return JsonResponse(
        {
            "ok": True,
            "date": data.get("date"),
            "meal": data.get("meal"),
            "barcode": data.get("barcode"),
            "mode": data.get("mode"),
            "candidates": slim,
        },
        status=200,
    )


@csrf_exempt
@require_POST
def api_barcode_commit(request):
    """
    draft_id + candidate_id(s)로 선택된 바코드 결과를
    FOOD_TB -> CUS_FOOD_TH/TS에 저장하고,
    저장 성공 후 recommend_and_commit()을 호출해 MENU_RECOM_TH까지 저장한다.

    ✅ 1번(검색 저장 버튼) 형태를 유지:
    - TH/TS는 atomic 내부에서 upsert + delete/insert로 덮어쓰기
    - 추천 실패해도 저장 성공은 유지
    """
    body = _parse_body_json(request)

    # 0) 입력 파싱(폼/JSON 모두 대응)
    draft_id = (request.POST.get("draft_id") or "").strip() or str(
        body.get("draft_id", "")
    ).strip()

    candidate_id = (request.POST.get("candidate_id") or "").strip() or str(
        body.get("candidate_id", "")
    ).strip()

    candidate_ids = request.POST.getlist("candidate_ids")
    if not candidate_ids:
        candidate_ids = body.get("candidate_ids") or []
    candidate_ids = [str(x).strip() for x in candidate_ids if str(x).strip()]

    if not candidate_ids and candidate_id:
        candidate_ids = [candidate_id]

    if not draft_id or not candidate_ids:
        return JsonResponse(
            {
                "ok": False,
                "error": "BAD_REQUEST",
                "message": "draft_id와 candidate_ids가 필요합니다.",
            },
            status=400,
        )

    # 1) 세션 draft 로드
    session_key = f"barcode_draft:{draft_id}"
    data = request.session.get(session_key)
    if not data:
        return JsonResponse(
            {"ok": False, "error": "DRAFT_NOT_FOUND", "message": "draft not found"},
            status=404,
        )

    candidates = data.get("candidates", []) or []

    # 2) picked_list 구성
    picked_list = []
    for cid in candidate_ids:
        picked = next(
            (c for c in candidates if str(c.get("candidate_id", "")).strip() == cid),
            None,
        )
        if picked:
            picked_list.append(picked)

    if not picked_list:
        return JsonResponse(
            {"ok": False, "error": "BAD_REQUEST", "detail": "picked_list empty"},
            status=400,
        )

    # 3) 저장 키(세션) 가져오기
    cust_id = getattr(request.user, "cust_id", None) or request.session.get("cust_id")
    rgs_dt = _normalize_rgs_dt_yyyymmdd(request.session.get("rgs_dt"))
    time_slot = _normalize_time_slot(request.session.get("time_slot"))
    seq = request.session.get("seq")

    # seq 보정: 동일 (cust_id,rgs_dt,time_slot) 있으면 그 seq 재사용
    try:
        with transaction.atomic():
            existing = (
                CusFoodTh.objects.select_for_update()
                .filter(cust_id=cust_id, rgs_dt=rgs_dt, time_slot=time_slot)
                .first()
            )
            if existing:
                seq = existing.seq
            else:
                seq = int(seq or 1)
    except Exception:
        seq = int(seq or 1)

    try:
        seq = int(seq)
    except Exception:
        seq = None

    if not (cust_id and rgs_dt and seq and time_slot):
        return JsonResponse(
            {
                "ok": False,
                "error": "SESSION_MISSING",
                "detail": "cust_id/rgs_dt/seq/time_slot",
            },
            status=400,
        )

    # 4) 영양값 merge 정책(1번 로직 유지 + 안전 merge)
    def _has_val(v):
        return v not in (None, "")

    body_kcal = body.get("kcal")
    body_carb = body.get("carb_g")
    body_prot = body.get("protein_g")
    body_fat = body.get("fat_g")

    apply_body_nutr = (len(picked_list) == 1) and (
        _has_val(body_kcal)
        or _has_val(body_carb)
        or _has_val(body_prot)
        or _has_val(body_fat)
    )

    cleaned = []
    for p in picked_list:
        name = (p.get("name") or "").strip()

        cand_kcal = p.get("kcal")
        cand_carb = p.get("carb_g")
        cand_prot = p.get("protein_g")
        cand_fat = p.get("fat_g")

        raw_kcal = body_kcal if (apply_body_nutr and _has_val(body_kcal)) else cand_kcal
        raw_carb = body_carb if (apply_body_nutr and _has_val(body_carb)) else cand_carb
        raw_prot = body_prot if (apply_body_nutr and _has_val(body_prot)) else cand_prot
        raw_fat = body_fat if (apply_body_nutr and _has_val(body_fat)) else cand_fat

        if (
            raw_kcal in (None, "")
            or raw_carb in (None, "")
            or raw_prot in (None, "")
            or raw_fat in (None, "")
        ):
            return JsonResponse(
                {
                    "ok": False,
                    "error": "NUTRITION_MISSING",
                    "detail": f"name={name}",
                    "missing_fields": [
                        *([] if raw_kcal not in (None, "") else ["kcal"]),
                        *([] if raw_carb not in (None, "") else ["carb_g"]),
                        *([] if raw_prot not in (None, "") else ["protein_g"]),
                        *([] if raw_fat not in (None, "") else ["fat_g"]),
                    ],
                },
                status=400,
            )

        name = _normalize_food_name(name)

        # 숫자화(기존 함수 형태 유지)
        kcal = to_int_trunc(raw_kcal, default=0)
        carb_g = to_int_trunc(raw_carb, default=0)
        protein_g = to_int_trunc(raw_prot, default=0)
        fat_g = to_int_trunc(raw_fat, default=0)

        # 최소 검증(전부 0이면 잘못 입력 가능성이 높음)
        if kcal == 0 and carb_g == 0 and protein_g == 0 and fat_g == 0:
            return JsonResponse(
                {"ok": False, "error": "INVALID_NUTRITION", "detail": f"name={name}"},
                status=400,
            )

        mr_c, mr_p, mr_f = macro_ratio_10(carb_g, protein_g, fat_g)

        food_id, _created_new = _get_or_create_food_id_by_name(
            name=name,
            kcal=kcal,
            carb_g=carb_g,
            protein_g=protein_g,
            fat_g=fat_g,
            mr_c=mr_c,
            mr_p=mr_p,
            mr_f=mr_f,
        )

        cleaned.append(
            {
                "name": name,
                "kcal": kcal,
                "carb_g": carb_g,
                "protein_g": protein_g,
                "fat_g": fat_g,
                "food_id": int(food_id),
            }
        )

    if not cleaned:
        return JsonResponse({"ok": False, "error": "NO_VALID_ITEMS"}, status=400)

    t = now14()

    # 추천에 필요한 값(저장 성공 후 실행)
    feel_mood = ""
    feel_energy = ""
    reco_rgs_dt = ""
    reco_time_slot = ""
    recent_food_names = []

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:

                # (A) CUS_FEEL_TH 존재 + mood/energy 확보(추천 입력)
                cursor.execute(
                    """
                    SELECT mood, energy
                    FROM CUS_FEEL_TH
                    WHERE cust_id=%s AND rgs_dt=%s AND seq=%s AND time_slot=%s
                    LIMIT 1
                    """,
                    [cust_id, rgs_dt, seq, time_slot],
                )
                row = cursor.fetchone()
                if row is None:
                    return JsonResponse(
                        {"ok": False, "error": "CUS_FEEL_TH_NOT_FOUND"}, status=404
                    )

                feel_mood = (row[0] or "").strip().lower()
                feel_energy = (row[1] or "").strip().lower()

                new_food_ids = [x["food_id"] for x in cleaned]

                total_kcal = sum(int(x["kcal"] or 0) for x in cleaned)
                total_carb = sum(int(x["carb_g"] or 0) for x in cleaned)
                total_prot = sum(int(x["protein_g"] or 0) for x in cleaned)
                total_fat = sum(int(x["fat_g"] or 0) for x in cleaned)

                # (B) TH upsert
                cursor.execute(
                    """
                    SELECT 1 FROM CUS_FOOD_TH
                    WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                    LIMIT 1
                    """,
                    [cust_id, rgs_dt, seq],
                )
                exists_th = cursor.fetchone() is not None

                if not exists_th:
                    cursor.execute(
                        """
                        INSERT INTO CUS_FOOD_TH
                        (created_time, updated_time, cust_id, rgs_dt, seq, time_slot, kcal, carb_g, protein_g, fat_g)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        [
                            t,
                            t,
                            cust_id,
                            rgs_dt,
                            seq,
                            time_slot,
                            total_kcal,
                            total_carb,
                            total_prot,
                            total_fat,
                        ],
                    )
                    th_action = "insert"
                else:
                    cursor.execute(
                        """
                        UPDATE CUS_FOOD_TH
                        SET updated_time=%s,
                            time_slot=%s,
                            kcal=%s, carb_g=%s, protein_g=%s, fat_g=%s
                        WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                        """,
                        [
                            t,
                            time_slot,
                            total_kcal,
                            total_carb,
                            total_prot,
                            total_fat,
                            cust_id,
                            rgs_dt,
                            seq,
                        ],
                    )
                    th_action = "update"

                # (C) TS 덮어쓰기
                cursor.execute(
                    """
                    DELETE FROM CUS_FOOD_TS
                    WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                    """,
                    [cust_id, rgs_dt, seq],
                )
                deleted_ts = cursor.rowcount

                ts_rows = []
                for i, food_id in enumerate(new_food_ids, start=1):
                    ts_rows.append((t, t, cust_id, rgs_dt, seq, i, food_id))

                cursor.executemany(
                    """
                    INSERT INTO CUS_FOOD_TS
                    (created_time, updated_time, cust_id, rgs_dt, seq, food_seq, food_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    ts_rows,
                )

                # (D) 추천 대상 slot/rgs_dt + recent foods
                reco_rgs_dt, reco_time_slot = _derive_reco_target(rgs_dt, time_slot)
                recent_food_names = _fetch_recent_food_names(cursor, cust_id, limit=10)

                # (E) ✅ “commit 이후 추천 실행” 등록
                def _run_reco_after_commit():
                    try:
                        if reco_time_slot and feel_mood and feel_energy:
                            # ✅ lazy import: 추천이 필요한 순간에만 import
                            from ml.menu_reco.service import recommend_and_commit

                            recommend_and_commit(
                                cust_id=str(cust_id),
                                mood=str(feel_mood).strip().lower(),
                                energy=str(feel_energy).strip().lower(),
                                rgs_dt=str(reco_rgs_dt),
                                rec_time_slot=str(reco_time_slot).strip().upper(),
                                current_food=None,
                                recent_foods=(
                                    recent_food_names[:10]
                                    if recent_food_names
                                    else None
                                ),
                            )
                    except Exception:
                        # 저장 성공은 유지 (추천 실패는 별도로 삼킴)
                        return

                transaction.on_commit(_run_reco_after_commit)

        # 저장 성공 시 draft 제거
        request.session.pop(session_key, None)
        request.session.modified = True

        return JsonResponse(
            {
                "ok": True,
                "th_action": th_action,
                "deleted_ts": deleted_ts,
                "inserted_ts": len(new_food_ids),
                "cust_id": cust_id,
                "rgs_dt": rgs_dt,
                "seq": seq,
                "time_slot": time_slot,
                "food_ids": new_food_ids,
                "redirect_url": "/record/meal/",
                # 참고용(프론트 디버깅/로그용)
                "reco_rgs_dt": reco_rgs_dt,
                "reco_time_slot": reco_time_slot,
            },
            status=200,
        )

    except Exception as e:
        return JsonResponse(
            {"ok": False, "error": "DB_SAVE_FAILED", "detail": str(e)}, status=500
        )


import traceback


# =========================
# 3) Food Search API
# =========================
@require_GET
def api_food_search(request):
    try:
        print(
            "[API_FOOD_SEARCH][ENTER]",
            "method=",
            request.method,
            "path=",
            request.path,
            "q=",
            request.GET.get("q"),
            "user_auth=",
            getattr(request.user, "is_authenticated", None),
            "user_cust_id=",
            getattr(request.user, "cust_id", None),
            flush=True,
        )

        q = (request.GET.get("q") or "").strip()
        if not q:
            return JsonResponse({"q": q, "count": 0, "items": []}, status=200)

        qs = (
            FoodTb.objects.filter(name__icontains=q)
            .order_by("name")
            .values("food_id", "name", "kcal", "carb_g", "protein_g", "fat_g")[:200]
        )

        items = []
        for row in qs:
            items.append(
                {
                    "food_id": row["food_id"],
                    "name": row["name"],
                    "kcal": 0.0 if row["kcal"] is None else float(row["kcal"]),
                    "carb_g": 0.0 if row["carb_g"] is None else float(row["carb_g"]),
                    "protein_g": (
                        0.0 if row["protein_g"] is None else float(row["protein_g"])
                    ),
                    "fat_g": 0.0 if row["fat_g"] is None else float(row["fat_g"]),
                }
            )

        return JsonResponse({"q": q, "count": len(items), "items": items}, status=200)
    except Exception as e:
        print("[API_FOOD_SEARCH][EXC]", repr(e), flush=True)
        traceback.print_exc()
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


def get_cust_id(request) -> str:
    cust_id = request.session.get("cust_id")
    if not cust_id:
        raise ValueError("cust_id missing (session)")
    return str(cust_id).strip()


@require_POST
def api_meal_add(request):
    """
    payload:
    {
      "rgs_dt": "2025-12-17",
      "time_slot": "M",
      "food_ids": [101, 205, 333]
    }
    """
    try:
        cust_id = get_cust_id(request)
        payload = json.loads(request.body.decode("utf-8"))

        rgs_dt = (payload.get("rgs_dt") or "").strip()
        time_slot = (payload.get("time_slot") or "").strip()
        food_ids = payload.get("food_ids") or []

        rgs_dt = _normalize_rgs_dt_yyyymmdd(rgs_dt)
        time_slot = _normalize_time_slot(time_slot)

        if not rgs_dt or not time_slot:
            return JsonResponse(
                {"ok": False, "error": "rgs_dt/time_slot required"}, status=400
            )
        if not isinstance(food_ids, list) or len(food_ids) == 0:
            return JsonResponse({"ok": False, "error": "food_ids required"}, status=400)

        # 중복 제거 + 정수화
        food_ids = list(dict.fromkeys([int(x) for x in food_ids]))

        t = now14()

        with transaction.atomic():
            # 1) 같은 날짜/끼니면 같은 seq 재사용, 아니면 새 발급
            new_seq = _get_or_create_food_seq_for_slot(
                cust_id=cust_id, rgs_dt=rgs_dt, time_slot=time_slot
            )

            # 2) FOOD_TB에서 영양정보 확정 조회 (서버 기준)
            foods = list(
                FoodTb.objects.filter(food_id__in=food_ids).values(
                    "food_id", "kcal", "carb_g", "protein_g", "fat_g"
                )
            )
            found = {f["food_id"] for f in foods}
            missing = [fid for fid in food_ids if fid not in found]
            if missing:
                return JsonResponse(
                    {"ok": False, "error": f"food_id not found: {missing}"}, status=400
                )

            # 3) totals 계산 (TH에 저장할 합계)
            food_map = {f["food_id"]: f for f in foods}

            total_kcal = 0
            total_carb = 0
            total_prot = 0
            total_fat = 0

            for fid in food_ids:
                f = food_map[fid]
                total_kcal += int(f["kcal"] or 0)
                total_carb += int(f["carb_g"] or 0)
                total_prot += int(f["protein_g"] or 0)
                total_fat += int(f["fat_g"] or 0)

            # 4) TH INSERT (한 끼 헤더)
            CusFoodTh.objects.update_or_create(
                cust_id=cust_id,
                rgs_dt=rgs_dt,
                seq=new_seq,
                defaults={
                    "updated_time": t,
                    "time_slot": time_slot,
                    "kcal": total_kcal,
                    "carb_g": total_carb,
                    "protein_g": total_prot,
                    "fat_g": total_fat,
                    # created_time은 insert일 때만 자동 설정되도록 모델 default가 없다면 아래처럼:
                    "created_time": t,
                },
            )

            # 5) TS INSERT (끼니 음식 목록)
            ts_rows = []
            for idx, fid in enumerate(food_ids, start=1):
                ts_rows.append(
                    CusFoodTs(
                        created_time=t,
                        updated_time=t,
                        cust_id=cust_id,
                        rgs_dt=rgs_dt,
                        seq=new_seq,
                        food_seq=idx,
                        food_id=fid,
                    )
                )
            CusFoodTs.objects.bulk_create(ts_rows)

        return JsonResponse(
            {"ok": True, "seq": new_seq, "inserted": len(food_ids)}, status=200
        )

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_GET
def api_meals_recent3(request):
    try:
        cust_id = get_cust_id(request)
        rgs_dt = (request.GET.get("rgs_dt") or "").strip()
        time_slot = (request.GET.get("time_slot") or "").strip()

        if not rgs_dt:
            return JsonResponse({"ok": False, "error": "rgs_dt required"}, status=400)

        th_qs = CusFoodTh.objects.filter(cust_id=cust_id, rgs_dt=rgs_dt)
        if time_slot:
            th_qs = th_qs.filter(time_slot=time_slot)

        th_rows = list(th_qs.order_by("-seq")[:3])
        seqs = [r.seq for r in th_rows]

        ts_rows = list(
            CusFoodTs.objects.filter(cust_id=cust_id, rgs_dt=rgs_dt, seq__in=seqs)
            .order_by("seq", "food_seq")
            .values("seq", "food_seq", "food_id")
        )

        food_ids = list({x["food_id"] for x in ts_rows})
        food_map = {
            f.food_id: f.name for f in FoodTb.objects.filter(food_id__in=food_ids)
        }

        foods_by_seq = {}
        for x in ts_rows:
            foods_by_seq.setdefault(x["seq"], []).append(
                {
                    "food_seq": x["food_seq"],
                    "food_id": x["food_id"],
                    "name": food_map.get(x["food_id"], ""),
                }
            )

        meals = []
        for r in th_rows:
            meals.append(
                {
                    "rgs_dt": r.rgs_dt,
                    "seq": r.seq,
                    "time_slot": r.time_slot,
                    "totals": {
                        "kcal": r.kcal or 0,
                        "carb_g": r.carb_g or 0,
                        "protein_g": r.protein_g or 0,
                        "fat_g": r.fat_g or 0,
                    },
                    "foods": foods_by_seq.get(r.seq, []),
                }
            )

        return JsonResponse({"ok": True, "meals": meals}, status=200)

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_POST
def api_meal_save_by_search(request):
    try:
        cust_id = request.user.cust_id

        rgs_dt = request.session.get("rgs_dt")
        seq = request.session.get("seq")
        time_slot = request.session.get("time_slot")

        time_slot = _normalize_time_slot(time_slot)
        rgs_dt = _normalize_rgs_dt_yyyymmdd(rgs_dt)

        if not (rgs_dt and seq and time_slot):
            return JsonResponse(
                {"ok": False, "error": "session missing (rgs_dt/seq/time_slot)"},
                status=400,
            )

        seq = int(seq)
        t = now14()

        payload = json.loads(request.body.decode("utf-8"))
        food_ids = payload.get("food_ids") or []
        if not isinstance(food_ids, list) or len(food_ids) == 0:
            return JsonResponse({"ok": False, "error": "food_ids required"}, status=400)

        food_ids = list(dict.fromkeys([int(x) for x in food_ids]))

        # 추천에 쓸 변수들
        feel_mood = ""
        feel_energy = ""
        reco_rgs_dt = ""
        reco_time_slot = ""
        recent_food_names = []

        with transaction.atomic():
            with connection.cursor() as cursor:

                # ✅ 1) CUS_FEEL_TH에서 mood/energy 확보 (추천 입력)
                cursor.execute(
                    """
                    SELECT mood, energy
                    FROM CUS_FEEL_TH
                    WHERE cust_id=%s AND rgs_dt=%s AND seq=%s AND time_slot=%s
                    LIMIT 1
                    """,
                    [cust_id, rgs_dt, seq, time_slot],
                )
                row = cursor.fetchone()
                if row is None:
                    return JsonResponse(
                        {
                            "ok": False,
                            "error": "CUS_FEEL_TH row not found for current key",
                        },
                        status=404,
                    )

                feel_mood = (row[0] or "").strip().lower()
                feel_energy = (row[1] or "").strip().lower()

                # 2) FOOD_TB 영양 조회
                in_ph = ",".join(["%s"] * len(food_ids))
                cursor.execute(
                    f"""
                    SELECT food_id, kcal, carb_g, protein_g, fat_g
                    FROM FOOD_TB
                    WHERE food_id IN ({in_ph})
                    """,
                    food_ids,
                )
                foods = cursor.fetchall()

                found = {int(r[0]) for r in foods}
                missing = [fid for fid in food_ids if fid not in found]
                if missing:
                    return JsonResponse(
                        {"ok": False, "error": f"FOOD_TB missing food_id: {missing}"},
                        status=400,
                    )

                total_kcal = sum(int(r[1] or 0) for r in foods)
                total_carb = sum(int(r[2] or 0) for r in foods)
                total_prot = sum(int(r[3] or 0) for r in foods)
                total_fat = sum(int(r[4] or 0) for r in foods)

                # 3) TH upsert
                cursor.execute(
                    """
                    SELECT 1 FROM CUS_FOOD_TH
                    WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                    LIMIT 1
                    """,
                    [cust_id, rgs_dt, seq],
                )
                exists_th = cursor.fetchone() is not None

                if not exists_th:
                    cursor.execute(
                        """
                        INSERT INTO CUS_FOOD_TH
                        (created_time, updated_time, cust_id, rgs_dt, seq, time_slot, kcal, carb_g, protein_g, fat_g)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        [
                            t,
                            t,
                            cust_id,
                            rgs_dt,
                            seq,
                            time_slot,
                            total_kcal,
                            total_carb,
                            total_prot,
                            total_fat,
                        ],
                    )
                    th_action = "insert"
                else:
                    cursor.execute(
                        """
                        UPDATE CUS_FOOD_TH
                        SET updated_time=%s,
                            time_slot=%s,
                            kcal=%s,
                            carb_g=%s,
                            protein_g=%s,
                            fat_g=%s
                        WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                        """,
                        [
                            t,
                            time_slot,
                            total_kcal,
                            total_carb,
                            total_prot,
                            total_fat,
                            cust_id,
                            rgs_dt,
                            seq,
                        ],
                    )
                    th_action = "update"

                # 4) TS 덮어쓰기
                cursor.execute(
                    """
                    DELETE FROM CUS_FOOD_TS
                    WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                    """,
                    [cust_id, rgs_dt, seq],
                )
                deleted_ts = cursor.rowcount

                ts_rows = [
                    (t, t, cust_id, rgs_dt, seq, i, fid)
                    for i, fid in enumerate(food_ids, start=1)
                ]
                cursor.executemany(
                    """
                    INSERT INTO CUS_FOOD_TS
                    (created_time, updated_time, cust_id, rgs_dt, seq, food_seq, food_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    ts_rows,
                )

                # ✅ 5) 추천 대상 slot/rgs_dt + recent foods
                reco_rgs_dt, reco_time_slot = _derive_reco_target(rgs_dt, time_slot)
                recent_food_names = _fetch_recent_food_names(cursor, cust_id, limit=10)

                # ✅ 6) commit 이후 추천 실행 (추천 실패해도 저장 성공 유지)
                def _run_reco_after_commit():
                    try:
                        if reco_time_slot and feel_mood and feel_energy:
                            # ✅ lazy import
                            from ml.menu_reco.service import recommend_and_commit

                            recommend_and_commit(
                                cust_id=str(cust_id),
                                mood=str(feel_mood).strip().lower(),
                                energy=str(feel_energy).strip().lower(),
                                rgs_dt=str(reco_rgs_dt),
                                rec_time_slot=str(reco_time_slot).strip().upper(),
                                current_food=None,
                                recent_foods=(
                                    recent_food_names[:10]
                                    if recent_food_names
                                    else None
                                ),
                            )
                    except Exception:
                        return

                transaction.on_commit(_run_reco_after_commit)

        return JsonResponse(
            {
                "ok": True,
                "th_action": th_action,
                "deleted_ts": deleted_ts,
                "inserted_ts": len(food_ids),
                "cust_id": cust_id,
                "rgs_dt": rgs_dt,
                "seq": seq,
                "time_slot": time_slot,
                "reco_rgs_dt": reco_rgs_dt,
                "reco_time_slot": reco_time_slot,
            },
            status=200,
        )

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


# OCR 관련
@csrf_exempt
@require_POST
def api_ocr_job_create(request):

    try:
        image = request.FILES.get("image")
        if not image:
            return JsonResponse({"ok": False, "error": "IMAGE_REQUIRED"}, status=400)

        # cust_id
        cust_id = getattr(request.user, "cust_id", None) or request.session.get(
            "cust_id"
        )
        if not cust_id:
            return JsonResponse({"ok": False, "error": "CUST_ID_REQUIRED"}, status=400)

        # context
        rgs_dt = (
            request.POST.get("rgs_dt") or request.session.get("rgs_dt") or ""
        ).strip()
        time_slot = (
            request.POST.get("time_slot") or request.session.get("time_slot") or ""
        ).strip()
        seq_raw = request.POST.get("seq") or request.session.get("seq") or "1"

        try:
            seq = int(seq_raw)
        except Exception:
            return JsonResponse({"ok": False, "error": "SEQ_INVALID"}, status=400)

        if not rgs_dt or not time_slot:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "CTX_REQUIRED",
                    "detail": {"rgs_dt": rgs_dt, "time_slot": time_slot},
                },
                status=400,
            )

        # bucket
        bucket = (os.getenv("AWS_S3_BUCKET") or "").strip()
        if not bucket:
            return JsonResponse(
                {"ok": False, "error": "AWS_S3_BUCKET_MISSING"}, status=400
            )
        filename = f"nutrition_{now14()}_{uuid.uuid4().hex[:8]}.jpg"
        env = get_env_name()
        key = build_ocr_input_key(
            env=env,
            cust_id=str(cust_id),
            rgs_dt=rgs_dt,
            seq=seq,
            filename=filename,
        )

        # 1️⃣ S3 upload
        try:
            upload_fileobj(
                fileobj=image.file,
                bucket=bucket,
                key=key,
                content_type=image.content_type or "image/jpeg",
            )
        except Exception as e:
            return JsonResponse(
                {"ok": False, "error": "S3_UPLOAD_FAILED", "detail": str(e)},
                status=500,
            )

        # 2️⃣ DB insert
        t = now14()

        try:
            with transaction.atomic(), connection.cursor() as cursor:
                max_try = 3
                last_error = None

                for _ in range(max_try):
                    cursor.execute(
                        """
                        SELECT COALESCE(MAX(ocr_seq), 0) + 1
                        FROM CUS_OCR_TH
                        WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                        """,
                        [cust_id, rgs_dt, seq],
                    )
                    ocr_seq = int(cursor.fetchone()[0])

                    try:
                        cursor.execute(
                            """
                            INSERT INTO CUS_OCR_TH
                            (cust_id, rgs_dt, seq, ocr_seq,
                             image_s3_bucket, image_s3_key,
                             success_yn, created_time, updated_time)
                            VALUES (%s,%s,%s,%s,%s,%s,'N',%s,%s)
                            """,
                            [cust_id, rgs_dt, seq, ocr_seq, bucket, key, t, t],
                        )
                        last_error = None
                        break
                    except Exception as e:
                        last_error = e
                        msg = str(e)
                        if "1062" in msg or "Duplicate entry" in msg:
                            continue
                        raise

                if last_error is not None:
                    raise last_error

        except Exception as e:
            return JsonResponse(
                {"ok": False, "error": "DB_INSERT_FAILED", "detail": str(e)},
                status=500,
            )

        # ✅ 정상 종료
        job_id = f"{cust_id}:{rgs_dt}:{seq}:{ocr_seq}"
        return JsonResponse(
            {"ok": True, "job_id": job_id, "bucket": bucket, "key": key}
        )

    except Exception as e:
        # ✅ 최상위 안전망
        return JsonResponse(
            {"ok": False, "error": "UNHANDLED_EXCEPTION", "detail": str(e)},
            status=500,
        )


@require_GET
def api_ocr_job_status(request):
    job_id = (request.GET.get("job_id") or "").strip()
    try:
        cust_id, rgs_dt, seq, ocr_seq = job_id.split(":")
        seq = int(seq)
        ocr_seq = int(ocr_seq)
    except Exception:
        return JsonResponse({"ok": False, "error": "JOB_ID_INVALID"}, status=400)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT success_yn, error_code, chosen_source, roi_score, full_score, updated_time
            FROM CUS_OCR_TH
            WHERE cust_id=%s AND rgs_dt=%s AND seq=%s AND ocr_seq=%s
            """,
            [cust_id, rgs_dt, seq, ocr_seq],
        )
        row = cursor.fetchone()

    if not row:
        return JsonResponse({"ok": False, "error": "JOB_NOT_FOUND"}, status=404)

    success_yn, error_code, chosen_source, roi_score, full_score, updated_time = row
    return JsonResponse(
        {
            "ok": True,
            "success_yn": success_yn,
            "error_code": error_code,
            "chosen_source": chosen_source,
            "roi_score": roi_score,
            "full_score": full_score,
            "updated_time": updated_time,
        }
    )


@require_GET
def api_ocr_job_result(request):
    job_id = (request.GET.get("job_id") or "").strip()
    try:
        cust_id, rgs_dt, seq, ocr_seq = job_id.split(":")
        seq = int(seq)
        ocr_seq = int(ocr_seq)
    except Exception:
        return JsonResponse({"ok": False, "error": "JOB_ID_INVALID"}, status=400)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT result_json
            FROM CUS_OCR_NUTR_TS
            WHERE cust_id=%s AND rgs_dt=%s AND seq=%s AND ocr_seq=%s
            """,
            [cust_id, rgs_dt, seq, ocr_seq],
        )
        row = cursor.fetchone()

    if not row:
        return JsonResponse(
            {"ok": False, "error": "비어있는 정보는 직접 입력해주세요."}, status=404
        )

    return JsonResponse({"ok": True, "result_json": row[0]})


@csrf_exempt
@require_POST
def api_ocr_commit_manual(request):
    """
    OCR 수동 입력 저장(바코드 저장 흐름과 동일한 최종 저장):
    - 사용자 입력 name + 영양정보(kcal/carb_g/protein_g/fat_g)
    - FOOD_TB: 동일/유사 이름이 있으면 재사용, 없으면 MAX(food_id)+1 생성
      - carb_g/protein_g/fat_g 소수점 버림 → 정수
      - Macro_ratio_c/p/f 합 10 계산 저장
    - CUS_FOOD_TH: upsert
    - CUS_FOOD_TS: 덮어쓰기(delete → insert)로 food_id 연결
    - CUS_OCR_TH: MANUAL 표시
    """

    # -------------------------
    # 0) Body 파싱(JSON/FORM 모두 허용)
    # -------------------------
    payload = None
    is_json = (request.content_type or "").startswith("application/json")
    if is_json:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            payload = {}

        def _get(key: str) -> str:
            v = payload.get(key)
            return "" if v is None else str(v)

    else:

        def _get(key: str) -> str:
            return request.POST.get(key) or ""

    # -------------------------
    # 1) job_id 파싱
    # -------------------------
    job_id = (_get("job_id") or "").strip()
    if not job_id:
        return JsonResponse({"ok": False, "error": "JOB_ID_REQUIRED"}, status=400)

    try:
        cust_id, rgs_dt, seq, ocr_seq = job_id.split(":")
        seq = int(seq)
        ocr_seq = int(ocr_seq)
    except Exception:
        return JsonResponse({"ok": False, "error": "JOB_ID_INVALID"}, status=400)

    # -------------------------
    # 2) 필수 context: time_slot
    # -------------------------
    time_slot = (_get("time_slot") or request.session.get("time_slot") or "").strip()
    if not time_slot:
        return JsonResponse({"ok": False, "error": "TIME_SLOT_REQUIRED"}, status=400)

    # -------------------------
    # 3) 사용자 입력 name + 영양값
    # -------------------------
    # 프론트 키가 name/product_name/food_name 중 무엇이든 수용
    name = (
        (_get("name") or "").strip()
        or (_get("product_name") or "").strip()
        or (_get("food_name") or "").strip()
    )
    if not name:
        return JsonResponse({"ok": False, "error": "NAME_REQUIRED"}, status=400)

    kcal_raw = _get("kcal")
    carb_raw = _get("carb_g")
    prot_raw = _get("protein_g")
    fat_raw = _get("fat_g")

    missing = []
    if str(kcal_raw).strip() == "":
        missing.append("kcal")
    if str(carb_raw).strip() == "":
        missing.append("carb_g")
    if str(prot_raw).strip() == "":
        missing.append("protein_g")
    if str(fat_raw).strip() == "":
        missing.append("fat_g")
    if missing:
        return JsonResponse(
            {"ok": False, "error": "NUTR_REQUIRED", "detail": {"missing": missing}},
            status=400,
        )

    # -------------------------
    # 4) 바코드와 동일한 정규화(소수점 버림, macro ratio 계산)
    # -------------------------
    name_n = _normalize_food_name(name)

    kcal_i = to_int_trunc(kcal_raw, default=0)
    carb_i = to_int_trunc(carb_raw, default=0)
    prot_i = to_int_trunc(prot_raw, default=0)
    fat_i = to_int_trunc(fat_raw, default=0)

    # 영양값이 전부 0이면 저장 의미가 없으니 막기(바코드와 동일 정책)
    if kcal_i == 0 and carb_i == 0 and prot_i == 0 and fat_i == 0:
        return JsonResponse(
            {"ok": False, "error": "INVALID_NUTRITION", "detail": {"name": name_n}},
            status=400,
        )

    mr_c, mr_p, mr_f = macro_ratio_10(carb_i, prot_i, fat_i)

    # -------------------------
    # 5) DB: FOOD_TB → TH upsert → TS 덮어쓰기 → OCR 이력 업데이트
    # -------------------------
    t = now14()

    try:
        with transaction.atomic(), connection.cursor() as cursor:

            # (A) FOOD_TB: get or create (동일/유사 이름 재사용, 없으면 MAX+1 신규)
            food_id, _created_new = _get_or_create_food_id_by_name(
                name=name_n,
                kcal=kcal_i,
                carb_g=carb_i,
                protein_g=prot_i,
                fat_g=fat_i,
                mr_c=mr_c,
                mr_p=mr_p,
                mr_f=mr_f,
            )

            # (B) CUS_FOOD_TH upsert (바코드 저장 로직과 동일 패턴)
            cursor.execute(
                """
                SELECT 1
                FROM CUS_FOOD_TH
                WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                LIMIT 1
                """,
                [cust_id, rgs_dt, seq],
            )
            exists_th = cursor.fetchone() is not None

            if not exists_th:
                cursor.execute(
                    """
                    INSERT INTO CUS_FOOD_TH
                    (created_time, updated_time, cust_id, rgs_dt, seq, time_slot,
                     kcal, carb_g, protein_g, fat_g)
                    VALUES
                    (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    [
                        t,
                        t,
                        cust_id,
                        rgs_dt,
                        seq,
                        time_slot,
                        kcal_i,
                        carb_i,
                        prot_i,
                        fat_i,
                    ],
                )
            else:
                cursor.execute(
                    """
                    UPDATE CUS_FOOD_TH
                    SET updated_time=%s,
                        time_slot=%s,
                        kcal=%s, carb_g=%s, protein_g=%s, fat_g=%s
                    WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                    """,
                    [t, time_slot, kcal_i, carb_i, prot_i, fat_i, cust_id, rgs_dt, seq],
                )

            # (C) CUS_FOOD_TS 덮어쓰기(delete → insert)
            cursor.execute(
                """
                DELETE FROM CUS_FOOD_TS
                WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                """,
                [cust_id, rgs_dt, seq],
            )

            cursor.execute(
                """
                INSERT INTO CUS_FOOD_TS
                (created_time, updated_time, cust_id, rgs_dt, seq, food_seq, food_id)
                VALUES
                (%s,%s,%s,%s,%s,%s,%s)
                """,
                [t, t, cust_id, rgs_dt, seq, 1, food_id],
            )

            # (D) CUS_OCR_TH: MANUAL 표시
            cursor.execute(
                """
                UPDATE CUS_OCR_TH
                SET updated_time=%s, success_yn='N', error_code='MANUAL'
                WHERE cust_id=%s AND rgs_dt=%s AND seq=%s AND ocr_seq=%s
                """,
                [t, cust_id, rgs_dt, seq, ocr_seq],
            )

        # 성공
        return JsonResponse(
            {
                "ok": True,
                "redirect_url": "/record/meal/",
                "food_id": int(food_id),
                "seq": int(seq),
            }
        )

    except Exception as e:
        return JsonResponse(
            {"ok": False, "error": "SAVE_FAILED", "detail": str(e)},
            status=500,
        )


def _normalize_ocr_nutrition_from_result_json(result_json: dict) -> dict:
    """
    result_json(= 너가 준 result_json 구조와 유사)을 받아
    parsed_nutrition에서 4대 영양소를 표준화해 반환.
    반환: {"kcal": float|None, "carb_g": float|None, "protein_g": float|None, "fat_g": float|None}
    """
    pn = (result_json or {}).get("parsed_nutrition") or {}

    def pick(key_kor: str, expected_unit: str):
        it = pn.get(key_kor) or {}
        if not it.get("found"):
            return None
        val = it.get("value")
        unit = it.get("unit")

        # 단위 가드(단위가 다르면 안전하게 None 처리 -> 사용자 입력 유도)
        if expected_unit and unit and unit != expected_unit:
            return None

        try:
            return float(val)
        except Exception:
            return None

    return {
        "kcal": pick("열량", "kcal"),
        "carb_g": pick("탄수화물", "g"),
        "protein_g": pick("단백질", "g"),
        "fat_g": pick("지방", "g"),
    }


@require_GET
def api_ocr_latest(request):
    """
    GET /record/api/ocr/latest/?rgs_dt=YYYYMMDD&seq=1
    - CUS_OCR_TH에서 최신 ocr_seq 조회
    - CUS_OCR_NUTR_TS에서 result_json 조회
    - 4대 영양소만 표준화해서 반환
    """
    cust_id = getattr(request.user, "cust_id", None) or request.session.get("cust_id")
    if not cust_id:
        return JsonResponse({"ok": False, "error": "CUST_ID_REQUIRED"}, status=400)

    rgs_dt = (request.GET.get("rgs_dt") or request.session.get("rgs_dt") or "").strip()
    seq_raw = (request.GET.get("seq") or request.session.get("seq") or "").strip()

    rgs_dt = _normalize_rgs_dt_yyyymmdd(rgs_dt)
    try:
        seq = int(seq_raw)
    except Exception:
        return JsonResponse({"ok": False, "error": "SEQ_INVALID"}, status=400)

    # 1) 최신 ocr_seq (성공/완료 우선)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT ocr_seq, chosen_source, roi_score, full_score, image_s3_bucket, image_s3_key
            FROM CUS_OCR_TH
            WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
              AND success_yn='Y'
              AND (status IS NULL OR status IN ('DONE','SUCCESS','COMPLETED'))
            ORDER BY ocr_seq DESC, updated_time DESC
            LIMIT 1
            """,
            [cust_id, rgs_dt, seq],
        )
        row = cursor.fetchone()

    if not row:
        # success_yn='Y'가 아직 안 찍히는 단계라면 최신 전체로 fallback도 가능
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ocr_seq, chosen_source, roi_score, full_score, image_s3_bucket, image_s3_key
                FROM CUS_OCR_TH
                WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                ORDER BY ocr_seq DESC, updated_time DESC
                LIMIT 1
                """,
                [cust_id, rgs_dt, seq],
            )
            row = cursor.fetchone()

    if not row:
        return JsonResponse({"ok": False, "error": "OCR_NOT_FOUND"}, status=404)

    ocr_seq, chosen_source, roi_score, full_score, bkt, key = row

    # 2) result_json 조회
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT result_json
            FROM CUS_OCR_NUTR_TS
            WHERE cust_id=%s AND rgs_dt=%s AND seq=%s AND ocr_seq=%s
            """,
            [cust_id, rgs_dt, seq, ocr_seq],
        )
        r2 = cursor.fetchone()

    if not r2:
        return JsonResponse(
            {"ok": False, "error": "비어있는 정보는 직접 입력해주세요."}, status=404
        )

    result_json = r2[0]
    if isinstance(result_json, str):
        try:
            result_json = json.loads(result_json)
        except Exception:
            return JsonResponse(
                {"ok": False, "error": "INVALID_result_json"}, status=500
            )

    nutrition = _normalize_ocr_nutrition_from_result_json(result_json)
    missing = [k for k, v in nutrition.items() if v is None]

    return JsonResponse(
        {
            "ok": True,
            "cust_id": str(cust_id),
            "rgs_dt": rgs_dt,
            "seq": seq,
            "ocr_seq": int(ocr_seq),
            "nutrition": nutrition,
            "missing_fields": missing,
            "meta": {
                "chosen_source": chosen_source,
                "roi_score": roi_score,
                "full_score": full_score,
                "image_s3_bucket": bkt,
                "image_s3_key": key,
            },
        },
        status=200,
    )
