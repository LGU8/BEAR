# record/views_api.py
import os
import re
import uuid
import json
import tempfile
import math
from pathlib import Path
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.db import connection, transaction
from django.db.models import Max, Value
from django.db.models.functions import Coalesce
from .services.storage.s3_client import upload_fileobj
from .services.storage.s3_paths import build_ocr_input_key, get_env_name

from ml.menu_reco.service import recommend_and_commit

from .services.barcode.total import run_barcode_pipeline
from .services.barcode.mapping_code import (
    EnvNotSetError,
    UpstreamAPIError,
    get_nutrition_by_report_no,
)


from .models import FoodTb, CusFoodTh, CusFoodTs
from .utils_time import now14


# 감정 기록 키워드 api
def keyword_api(request):
    """
    감정(mood) + 활성도(energy)에 따라
    키워드 목록을 DB에서 조회해서 JSON으로 반환
    """

    if request.method != "GET":
        return JsonResponse({"error": "GET method only"}, status=405)

    # 파라미터 받기
    mood = request.GET.get("mood")
    energy = request.GET.get("energy")

    if not mood or not energy:
        return JsonResponse({"error": "mood and energy are required"}, status=400)

    # SQL 작성
    sql = """
        SELECT word
        FROM COM_FEEL_TM
        WHERE cluster_val IN (SELECT cluster_val
            FROM COM_FEEL_CLUSTER_TM
            WHERE mood = %s
                AND energy = %s)
    """

    # SQL 실행
    with connection.cursor() as cursor:
        cursor.execute(sql, [mood, energy])
        rows = cursor.fetchall()

    keywords = [r[0] for r in rows]

    # JSON 응답
    return JsonResponse(keywords, safe=False)


def _normalize_candidate(raw):
    """
    mapping_code.get_product_info_by_barcode() 결과(C005) → 프론트/commit 공통 규격으로 정규화
    """
    return {
        "candidate_id": raw.get("candidate_id", ""),
        "name": raw.get("product_name", ""),
        "brand": raw.get("manufacturer", ""),
        "flavor": raw.get(
            "flavor", ""
        ),  # C005에는 flavor가 보통 없음 (있으면 채워도 됨)
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

    # 이미 M/L/D라면
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
    # 여러 공백을 하나로
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
):
    """
    FOOD_TB에 같은 name이 있으면 해당 food_id 반환
    없으면 새 food_id 생성 + FOOD_TB insert
    """
    name_n = _normalize_food_name(name)
    if not name_n:
        raise ValueError("food name is empty")

    with transaction.atomic():
        # 1) 같은 name이 이미 있으면 재사용
        existing = FoodTb.objects.filter(name=name_n).order_by("food_id").first()
        if existing:
            return existing.food_id, False

        # 2) 없으면 새 food_id 생성
        last_id = FoodTb.objects.aggregate(mx=Max("food_id"))["mx"] or 0
        new_id = int(last_id) + 1

        FoodTb.objects.create(
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
    (transaction.atomic + select_for_update와 함께 써야 안전)
    """
    # 같은 날짜/끼니(time_slot) 기존 seq 찾기
    existed = (
        CusFoodTh.objects.select_for_update()
        .filter(cust_id=cust_id, rgs_dt=rgs_dt, time_slot=time_slot)
        .order_by("-seq")
        .first()
    )
    if existed:
        return int(existed.seq)

    # 없으면 새 seq 발급 (cust_id 전체 기준)
    last_th = (
        CusFoodTh.objects.select_for_update()
        .filter(cust_id=cust_id)
        .order_by("-seq")
        .first()
    )
    return int((last_th.seq if last_th else 0) + 1)


@csrf_exempt
@require_POST
def api_barcode_scan(request):
    mode = request.POST.get("mode", "barcode")
    image = request.FILES.get("image")
    date = request.POST.get("date", "").strip()
    meal = request.POST.get("meal", "").strip()

    if not image:
        return JsonResponse(
            {"ok": False, "error": "IMAGE_REQUIRED", "message": "image is required"},
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
    candidates = [c for c in candidates if c.get("candidate_id")]  # 안전 필터

    print("=== DEBUG candidates ===")
    for c in candidates:
        print(c)
    print("========================")

    # ✅ 영양 merge 추가
    for c in candidates:
        report_no = (c.get("report_no") or "").strip()
        product_name = (c.get("name") or "").strip()

        if not report_no or not product_name:
            continue

        nutr = (
            get_nutrition_by_report_no(
                report_no,
                product_name=product_name,
            )
            or {}
        )

        print("[DEBUG] report_no:", report_no, "product_name:", product_name)
        print("[DEBUG] nutr:", nutr)

        c["kcal"] = nutr.get("kcal")
        c["carb_g"] = nutr.get("carb_g")
        c["protein_g"] = nutr.get("protein_g")
        c["fat_g"] = nutr.get("fat_g")

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

    draft_id = uuid.uuid4().hex
    request.session[f"barcode_draft:{draft_id}"] = {
        "date": date,
        "meal": meal,
        "barcode": barcode,
        "mode": mode,
        "candidates": candidates,  # commit에 필요하므로 full 저장
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

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"ok": False, "error": "INVALID_JSON"}, status=400)

    """
    /record/api/scan/commit/ (result.js가 호출)
    draft_id + candidate_id(s)로 선택된 바코드 결과를
    FOOD_TB -> CUS_FOOD_TH/TS에 저장한다.
    """
    print("[api_barcode_commit] HIT ✅")

    # 0) 입력 파싱 (기존 로직 유지):contentReference[oaicite:11]{index=11}
    draft_id = (request.POST.get("draft_id") or "").strip()
    candidate_id = (request.POST.get("candidate_id") or "").strip()
    candidate_ids = request.POST.getlist("candidate_ids")
    candidate_ids = [str(x).strip() for x in candidate_ids if str(x).strip()]

    if (not draft_id) or (not candidate_id and not candidate_ids):
        try:
            body = json.loads((request.body or b"{}").decode("utf-8"))
            draft_id = draft_id or str(body.get("draft_id", "")).strip()
            if not candidate_ids:
                candidate_ids = body.get("candidate_ids") or []
                candidate_ids = [
                    str(x).strip() for x in candidate_ids if str(x).strip()
                ]
            candidate_id = candidate_id or str(body.get("candidate_id", "")).strip()
        except Exception:
            pass

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

    # 1) 세션 draft 로드:contentReference[oaicite:12]{index=12}:contentReference[oaicite:13]{index=13}
    session_key = f"barcode_draft:{draft_id}"
    data = request.session.get(session_key)
    if not data:
        return JsonResponse(
            {"ok": False, "error": "DRAFT_NOT_FOUND", "message": "draft not found"},
            status=404,
        )

    candidates = data.get("candidates", [])

    # 2) 선택된 후보 picked_list 만들기 (기존 로직 유지):contentReference[oaicite:14]{index=14}
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

    # 3) 저장 키(감정/검색 세션) 가져오기: rgs_dt/seq/time_slot
    #    - api_scan_commit이 쓰는 방식과 동일:contentReference[oaicite:15]{index=15}
    cust_id = getattr(request.user, "cust_id", None) or request.session.get("cust_id")
    rgs_dt = request.session.get("rgs_dt")
    seq = request.session.get("seq")
    time_slot = request.session.get("time_slot")

    rgs_dt = _normalize_rgs_dt_yyyymmdd(rgs_dt)
    time_slot = _normalize_time_slot(time_slot)

    with transaction.atomic():
        existing = (
            CusFoodTh.objects.select_for_update()
            .filter(cust_id=cust_id, rgs_dt=rgs_dt, time_slot=time_slot)
            .first()
        )
        if existing:
            seq = existing.seq
        else:
            # FEEL/FOOD seq를 공유한다면, 세션 seq를 사용
            # (단, 세션 seq가 없다면 여기서 새로 발급)
            seq = int(seq or 1)

    if seq is not None:
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

    # 4) picked에서 영양값이 없으면 저장 불가(정책)
    #    ✅ 수정: candidate 값(p.get) + 사용자 입력(body) 값을 merge해서 최종 영양값을 만든다.
    #    - 원칙: body 값이 있으면 body 우선
    #    - body 값이 없으면 candidate 값 사용
    #    - 둘 다 없으면 NUTRITION_MISSING

    def _has_val(v):
        return v not in (None, "")

    # ✅ 프론트(result.js)가 보내는 영양값(단건 선택일 때 top-level로 옴)
    body_kcal = body.get("kcal")
    body_carb = body.get("carb_g")
    body_prot = body.get("protein_g")
    body_fat = body.get("fat_g")

    # ✅ 단건 선택(대부분 너 현재 UX)일 때만 top-level 영양값을 적용
    apply_body_nutr = (len(picked_list) == 1) and (
        _has_val(body_kcal)
        or _has_val(body_carb)
        or _has_val(body_prot)
        or _has_val(body_fat)
    )

    cleaned = []
    for p in picked_list:
        name = (p.get("name") or "").strip()

        # 후보의 원본 영양값
        cand_kcal = p.get("kcal")
        cand_carb = p.get("carb_g")
        cand_prot = p.get("protein_g")
        cand_fat = p.get("fat_g")

        # ✅ 최종 raw: body가 있으면 body 우선(단건 선택일 때), 아니면 candidate
        raw_kcal = body_kcal if (apply_body_nutr and _has_val(body_kcal)) else cand_kcal
        raw_carb = body_carb if (apply_body_nutr and _has_val(body_carb)) else cand_carb
        raw_prot = body_prot if (apply_body_nutr and _has_val(body_prot)) else cand_prot
        raw_fat = body_fat if (apply_body_nutr and _has_val(body_fat)) else cand_fat

        # ✅ 여기서 “merge 후” 누락 체크
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

        # 숫자화(기존 to_int_trunc 사용)
        name = _normalize_food_name(name)

        kcal = to_int_trunc(raw_kcal)
        carb_g = to_int_trunc(raw_carb)
        protein_g = to_int_trunc(raw_prot)
        fat_g = to_int_trunc(raw_fat)

        # ✅ 숫자화 결과 검증(사용자 입력이 "abc" 같은 경우 방어)
        if kcal is None or carb_g is None or protein_g is None or fat_g is None:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "INVALID_NUTRITION",
                    "detail": f"name={name}",
                },
                status=400,
            )

        # ✅ 합이 10인 비율 계산
        mr_c, mr_p, mr_f = macro_ratio_10(carb_g, protein_g, fat_g)

        # ✅ Step2: name 기준 food_id 재사용/생성
        food_id, created_new = _get_or_create_food_id_by_name(
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

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:

                # (선택) CUS_FEEL_TH 존재 검증 - api_scan_commit과 동일:contentReference[oaicite:16]{index=16}
                cursor.execute(
                    """
                    SELECT 1
                    FROM CUS_FEEL_TH
                    WHERE cust_id=%s AND rgs_dt=%s AND seq=%s AND time_slot=%s
                    LIMIT 1
                    """,
                    [cust_id, rgs_dt, seq, time_slot],
                )
                if cursor.fetchone() is None:
                    return JsonResponse(
                        {"ok": False, "error": "CUS_FEEL_TH_NOT_FOUND"}, status=404
                    )

                # 5) 결과 그대로 사용
                new_food_ids = [x["food_id"] for x in cleaned]

                # 6) totals 계산
                total_kcal = sum(int(x["kcal"] or 0) for x in cleaned)
                total_carb = sum(int(x["carb_g"] or 0) for x in cleaned)
                total_prot = sum(int(x["protein_g"] or 0) for x in cleaned)
                total_fat = sum(int(x["fat_g"] or 0) for x in cleaned)

                # 7) CUS_FOOD_TH upsert (time_slot 있음):contentReference[oaicite:17]{index=17}
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

                # 8) CUS_FOOD_TS 덮어쓰기 (time_slot 없음):contentReference[oaicite:18]{index=18}
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

        # 9) 성공 시 draft 제거 + 응답:contentReference[oaicite:19]{index=19}
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
            },
            status=200,
        )

    except Exception as e:
        return JsonResponse(
            {"ok": False, "error": "DB_SAVE_FAILED", "detail": str(e)}, status=500
        )


@require_GET
def api_food_search(request):
    q = (request.GET.get("q") or "").strip()

    # 1) 검색어가 비면 빈 결과 (원하면 "전체" 또는 "상위 N개"로 정책 변경 가능)
    if not q:
        return JsonResponse({"q": q, "count": 0, "items": []}, status=200)

    # 2) 검색: name에 q 포함
    # - Coalesce로 NULL이면 0.0 처리 (표 렌더링 시 안정적)
    qs = (
        FoodTb.objects.filter(name__icontains=q)
        .order_by("name")
        .values(
            "food_id",
            "name",
            "kcal",
            "carb_g",
            "protein_g",
            "fat_g",
        )[:200]
    )

    # 3) JSON 직렬화 안정화: None -> 0.0 (선택사항)
    #    DB에 NULL이 없으면 이 블록은 없어도 됨.
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

        # 1) session 키
        rgs_dt = request.session.get("rgs_dt")  # "YYYYMMDD"
        seq = request.session.get("seq")  # int or str
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

        # 2) body food_ids
        payload = json.loads(request.body.decode("utf-8"))
        food_ids = payload.get("food_ids") or []
        if not isinstance(food_ids, list) or len(food_ids) == 0:
            return JsonResponse({"ok": False, "error": "food_ids required"}, status=400)

        food_ids = list(dict.fromkeys([int(x) for x in food_ids]))  # 중복 제거

        # --- 추천에 쓸 변수(트랜잭션 내부에서 확보 → 트랜잭션 밖에서 실행)
        feel_mood = None
        feel_energy = None
        recent_food_names = []

        with transaction.atomic():
            with connection.cursor() as cursor:

                # (선택) 3) CUS_FEEL_TH 존재 검증
                cursor.execute(
                    """
                    SELECT 1
                    FROM CUS_FEEL_TH
                    WHERE cust_id=%s AND rgs_dt=%s AND seq=%s AND time_slot=%s
                    LIMIT 1
                    """,
                    [cust_id, rgs_dt, seq, time_slot],
                )
                if cursor.fetchone() is None:
                    return JsonResponse(
                        {
                            "ok": False,
                            "error": "CUS_FEEL_TH row not found for current key",
                        },
                        status=404,
                    )

                # 4) FOOD_TB 영양 조회
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

                # 5) totals 계산
                total_kcal = sum(int(r[1] or 0) for r in foods)
                total_carb = sum(int(r[2] or 0) for r in foods)
                total_prot = sum(int(r[3] or 0) for r in foods)
                total_fat = sum(int(r[4] or 0) for r in foods)

                # 6) TH upsert
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

                # 7) TS 덮어쓰기: delete 후 insert
                cursor.execute(
                    """
                    DELETE FROM CUS_FOOD_TS
                    WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                    """,
                    [cust_id, rgs_dt, seq],
                )
                deleted_ts = cursor.rowcount

                ts_rows = []
                for i, fid in enumerate(food_ids, start=1):
                    ts_rows.append((t, t, cust_id, rgs_dt, seq, i, fid))

                cursor.executemany(
                    """
                    INSERT INTO CUS_FOOD_TS
                    (created_time, updated_time, cust_id, rgs_dt, seq, food_seq, food_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    ts_rows,
                )

            # ============================
            # 추천 실행 + MENU_RECOM_TH 저장
            # ============================
            recom_ok = False
            recom_error = None
            try:
                # feel_mood/feel_energy가 이미 DB에 pos/neu/neg, low/med/hig로 저장돼 있다고 가정
                # time_slot은 세션에서 "M/L/D"로 이미 들어오므로 rec_time_slot으로 그대로 사용
                recommend_and_commit(
                    cust_id=str(cust_id),
                    mood=str(feel_mood).strip().lower(),
                    energy=str(feel_energy).strip().lower(),
                    rgs_dt=str(rgs_dt),
                    rec_time_slot=str(time_slot).strip().upper(),
                    current_food=None,  # 여러 개 선택이므로 단일 exclude는 비워두는 게 안전
                    recent_foods=recent_food_names[:10] if recent_food_names else None,
                )
                recom_ok = True
            except Exception as e:
                # 저장은 성공 유지, 추천만 실패
                recom_error = f"{type(e).__name__}: {e}"

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

        env = get_env_name()
        key = build_ocr_input_key(
            env=env,
            cust_id=str(cust_id),
            rgs_dt=rgs_dt,
            seq=seq,
            filename=image.name,
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
            SELECT nutr_json
            FROM CUS_OCR_NUTR_TS
            WHERE cust_id=%s AND rgs_dt=%s AND seq=%s AND ocr_seq=%s
            """,
            [cust_id, rgs_dt, seq, ocr_seq],
        )
        row = cursor.fetchone()

    if not row:
        return JsonResponse({"ok": False, "error": "RESULT_NOT_READY"}, status=404)

    return JsonResponse({"ok": True, "nutr_json": row[0]})


@csrf_exempt
@require_POST
def api_ocr_commit_manual(request):
    """
    OCR 실패/timeout 시 사용자가 직접 입력한 영양성분을 저장.
    - job_id로 cust_id/rgs_dt/seq/ocr_seq를 특정
    - CUS_FOOD_TH에 값 저장(기존 upsert 패턴)
    - (선택) CUS_OCR_TH에 error_code='MANUAL' 같은 표시도 가능
    """
    job_id = (request.POST.get("job_id") or "").strip()
    if not job_id:
        return JsonResponse({"ok": False, "error": "JOB_ID_REQUIRED"}, status=400)

    try:
        cust_id, rgs_dt, seq, ocr_seq = job_id.split(":")
        seq = int(seq)
        ocr_seq = int(ocr_seq)
    except Exception:
        return JsonResponse({"ok": False, "error": "JOB_ID_INVALID"}, status=400)

    def _to_int(x):
        try:
            return int(float(x))
        except Exception:
            return 0

    # 프론트에서 보내는 필드명 기준(필요하면 너 UI에 맞게 변경)
    kcal = _to_int(request.POST.get("kcal"))
    carb = _to_int(request.POST.get("carb_g"))
    prot = _to_int(request.POST.get("protein_g"))
    fat = _to_int(request.POST.get("fat_g"))
    time_slot = (
        request.POST.get("time_slot") or request.session.get("time_slot") or ""
    ).strip()

    if not time_slot:
        return JsonResponse({"ok": False, "error": "TIME_SLOT_REQUIRED"}, status=400)

    t = now14()

    try:
        with transaction.atomic(), connection.cursor() as cursor:
            # 1) CUS_FOOD_TH upsert(너 프로젝트 패턴 유지)
            cursor.execute(
                """
                SELECT 1 FROM CUS_FOOD_TH
                WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                LIMIT 1
                """,
                [cust_id, rgs_dt, seq],
            )
            exists = cursor.fetchone() is not None

            if not exists:
                cursor.execute(
                    """
                    INSERT INTO CUS_FOOD_TH
                    (created_time, updated_time, cust_id, rgs_dt, seq, time_slot, kcal, carb_g, protein_g, fat_g)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    [t, t, cust_id, rgs_dt, seq, time_slot, kcal, carb, prot, fat],
                )
            else:
                cursor.execute(
                    """
                    UPDATE CUS_FOOD_TH
                    SET updated_time=%s, time_slot=%s, kcal=%s, carb_g=%s, protein_g=%s, fat_g=%s
                    WHERE cust_id=%s AND rgs_dt=%s AND seq=%s
                    """,
                    [t, time_slot, kcal, carb, prot, fat, cust_id, rgs_dt, seq],
                )

            # 2) (선택) CUS_OCR_TH에 “수동처리됨” 표시
            cursor.execute(
                """
                UPDATE CUS_OCR_TH
                SET updated_time=%s, success_yn='N', error_code='MANUAL'
                WHERE cust_id=%s AND rgs_dt=%s AND seq=%s AND ocr_seq=%s
                """,
                [t, cust_id, rgs_dt, seq, ocr_seq],
            )

        return JsonResponse({"ok": True, "redirect_url": "/record/meal/"})

    except Exception as e:
        return JsonResponse(
            {"ok": False, "error": "SAVE_FAILED", "detail": str(e)}, status=500
        )


def to_int_trunc(v, default=0):
    """
    소수점 버림(int) 변환.
    - '12.9', 12.9, None, '' 등 안전 처리
    - 반올림 X, 그냥 버림 O
    """
    try:
        if v is None or v == "":
            return default
        return int(float(v))  # ✅ 소수점 버림
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

    raw = [
        carb_k / total * 10,
        prot_k / total * 10,
        fat_k / total * 10,
    ]

    base = [math.floor(x) for x in raw]
    remain = 10 - sum(base)

    # 소수점 큰 순서대로 1씩 배분
    frac = [(raw[i] - base[i], i) for i in range(3)]
    frac.sort(reverse=True)

    for i in range(remain):
        base[frac[i][1]] += 1

    return tuple(base)  # (carb10, protein10, fat10)
