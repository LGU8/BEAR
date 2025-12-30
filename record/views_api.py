# record/views_api.py
import uuid
import json
import tempfile
import numpy as np
import os
from pathlib import Path
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.db import connection, transaction
from django.db.models import Value
from django.db.models.functions import Coalesce
from src.ocr.pipeline import run_ocr_pipeline
from record.services.storage.s3_client import upload_fileobj
from record.services.storage.s3_paths import build_ocr_input_key, get_env_name

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
        WHERE cluster_val = (SELECT cluster_val
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


def _insert_menu_recom_th_rawsql(
    *, date: str, meal: str, barcode: str, picked: dict
) -> None:
    """
    ✅ DB 저장은 여기서만 수행 (mapping_code.py에는 저장 로직 없음)

    ⚠️ 아래 INSERT 컬럼은 '가장 흔한 구성' 가정.
    네 MENU_RECOM_TH 실제 컬럼/NOT NULL 제약에 맞춰 조정 필요할 수 있음. [^1]
    """
    now = datetime.now()

    candidate_id = (picked.get("candidate_id") or "").strip()
    name = (picked.get("name") or "").strip()
    brand = (picked.get("brand") or "").strip()
    flavor = (picked.get("flavor") or "").strip()
    report_no = (picked.get("report_no") or "").strip()

    if not candidate_id:
        raise ValueError("candidate_id가 비어있습니다.")
    if not date or not meal or not barcode:
        raise ValueError("date/meal/barcode가 비어있습니다.")

    raw_json = json.dumps(picked.get("raw", {}), ensure_ascii=False)

    # ✅ 최소 컬럼 가정 버전
    # - 네 테이블 컬럼이 다르면 여기 컬럼명을 맞춰야 함
    sql = """
    INSERT INTO MENU_RECOM_TH
      (created_time, updated_time, rgs_dt, time_slot, barcode, candidate_id, name, brand, flavor, report_no, raw_json)
    VALUES
      (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = [
        now,
        now,
        date,
        meal,
        barcode,
        candidate_id,
        name,
        brand,
        flavor,
        report_no,
        raw_json,
    ]

    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(sql, params)


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
    # FormData + JSON 둘 다 지원
    draft_id = (request.POST.get("draft_id") or "").strip()

    # ✅ 단건 호환
    candidate_id = (request.POST.get("candidate_id") or "").strip()

    # ✅ 다건 호환
    candidate_ids = request.POST.getlist("candidate_ids")  # FormData에서 여러 개
    candidate_ids = [str(x).strip() for x in candidate_ids if str(x).strip()]

    # JSON도 지원
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

    # ✅ 단건만 들어오면 리스트로 통일
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

    session_key = f"barcode_draft:{draft_id}"
    data = request.session.get(session_key)
    if not data:
        return JsonResponse(
            {"ok": False, "error": "DRAFT_NOT_FOUND", "message": "draft not found"},
            status=404,
        )

    candidates = data.get("candidates", [])

    # ✅ 선택된 후보들 찾기
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
            {"ok": False, "error": "DB_SAVE_FAILED", "detail": str(e)},
            status=500,
        )

    # ✅ DB 저장(여러 건)
    try:
        for picked in picked_list:
            _insert_menu_recom_th_rawsql(
                date=(data.get("date") or "").strip(),
                meal=(data.get("meal") or "").strip(),
                barcode=(data.get("barcode") or "").strip(),
                picked=picked,
            )
    except Exception as e:
        return JsonResponse(
            {"ok": False, "error": "DB_SAVE_FAILED", "detail": str(e)}, status=500
        )

    # ✅ 성공 시 draft 제거
    request.session.pop(session_key, None)
    request.session.modified = True

    return JsonResponse(
        {
            "ok": True,
            "date": data.get("date"),
            "meal": data.get("meal"),
            "barcode": data.get("barcode"),
            "picked": [
                {
                    "candidate_id": p.get("candidate_id", ""),
                    "name": p.get("name", ""),
                    "brand": p.get("brand", ""),
                    "flavor": p.get("flavor", ""),
                    "kcal": p.get("kcal"),
                    "carb_g": p.get("carb_g"),
                    "protein_g": p.get("protein_g"),
                    "fat_g": p.get("fat_g"),
                }
                for p in picked_list
            ],
        },
        status=200,
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


def get_cust_id(request) -> int:
    # ✅ 너 프로젝트 방식에 맞게 수정 (세션/로그인)
    cust_id = request.session.get("cust_id")
    if not cust_id:
        raise ValueError("cust_id missing (session)")
    return int(cust_id)


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
            # 1) 새 seq 발급 (cust_id 기준)
            last_th = (
                CusFoodTh.objects.select_for_update()
                .filter(cust_id=cust_id)
                .order_by("-seq")
                .first()
            )
            new_seq = (last_th.seq if last_th else 0) + 1

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
            CusFoodTh.objects.create(
                created_time=t,
                updated_time=t,
                cust_id=cust_id,
                rgs_dt=rgs_dt,
                seq=new_seq,
                time_slot=time_slot,
                kcal=total_kcal,
                carb_g=total_carb,
                protein_g=total_prot,
                fat_g=total_fat,
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
        time_slot = request.session.get("time_slot")  # "M/L/D"

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


def macro_ratio(kcal, carb_g, protein_g, fat_g):
    # 필요 없으면 0으로 저장해도 OK
    # 단순 비율(%) 예시: (탄/단/지 g 기준 or kcal 기준) 중 너 정책에 맞춰 바꿔도 됨
    # 여기서는 kcal 기여(탄4, 단4, 지9)를 기준으로 % 계산
    carb_k = max(0, int(carb_g or 0)) * 4
    prot_k = max(0, int(protein_g or 0)) * 4
    fat_k = max(0, int(fat_g or 0)) * 9
    total = carb_k + prot_k + fat_k
    if total <= 0:
        return 0, 0, 0
    return (
        int(round(carb_k * 100 / total)),
        int(round(prot_k * 100 / total)),
        int(round(fat_k * 100 / total)),
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


@require_POST
def api_scan_commit(request):
    """
    바코드 결과 저장:
    1) 선택된 품목들을 FOOD_TB에 저장하여 food_id 확보
    2) (cust_id,rgs_dt,seq,time_slot) 기준으로 CUS_FOOD_TH/TS 덮어쓰기 저장
    3) 성공 시 redirect_url 반환 (프론트에서 location.href)
    """
    try:
        cust_id = request.user.cust_id

        # ✅ 감정/시간 페이지에서 session으로 들고 온 값 (검색 저장과 동일하게 맞추기)
        rgs_dt = request.session.get("rgs_dt")  # "YYYYMMDD"
        seq = request.session.get("seq")  # int or str
        time_slot = request.session.get("time_slot")  # "M/L/D"

        if not (cust_id and rgs_dt and seq and time_slot):
            return JsonResponse(
                {
                    "ok": False,
                    "error": "session missing (cust_id/rgs_dt/seq/time_slot)",
                },
                status=400,
            )

        seq = int(seq)
        t = now14()

        payload = json.loads(request.body.decode("utf-8"))
        # 프론트에서 선택한 바코드 결과 리스트를 보내야 함
        # 예: { "items": [ {"name":"빈츠","kcal":563,"carb_g":62.5,"protein_g":8.75,"fat_g":28.75}, ... ] }
        items = payload.get("items") or []
        if not isinstance(items, list) or len(items) == 0:
            return JsonResponse({"ok": False, "error": "items required"}, status=400)

        # 선택된 것만 오도록 프론트에서 필터링하는 걸 추천
        # (여기서는 서버에서도 최소 검증)
        cleaned = []
        for it in items:
            name = (it.get("name") or "").strip()
            if not name:
                continue
            kcal = to_int_trunc(it.get("kcal"))
            carb_g = to_int_trunc(it.get("carb_g"))
            protein_g = to_int_trunc(it.get("protein_g"))
            fat_g = to_int_trunc(it.get("fat_g"))
            cleaned.append((name, kcal, carb_g, protein_g, fat_g))

        if not cleaned:
            return JsonResponse({"ok": False, "error": "no valid items"}, status=400)

        with transaction.atomic():
            with connection.cursor() as cursor:

                # (선택) CUS_FEEL_TH 존재 검증 - 현재 끼니 키가 유효한지 확인
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
                        {"ok": False, "error": "CUS_FEEL_TH row not found"}, status=404
                    )

                # 1) FOOD_TB insert or reuse (food_id 확보)
                new_food_ids = []

                for name, kcal, carb_g, protein_g, fat_g in cleaned:
                    mr_c, mr_p, mr_f = macro_ratio(kcal, carb_g, protein_g, fat_g)

                    # ✅ 1) 동일 row 존재 여부 체크
                    cursor.execute(
                        """
                        SELECT food_id
                        FROM FOOD_TB
                        WHERE name=%s AND kcal=%s AND carb_g=%s AND protein_g=%s AND fat_g=%s
                        AND Macro_ratio_c=%s AND Macro_ratio_p=%s AND Macro_ratio_f=%s
                        LIMIT 1
                        """,
                        [name, kcal, carb_g, protein_g, fat_g, mr_c, mr_p, mr_f],
                    )
                    row = cursor.fetchone()

                    if row:
                        food_id = int(row[0])
                    else:
                        # ✅ 2) 없으면 INSERT
                        cursor.execute(
                            """
                            INSERT INTO FOOD_TB
                            (created_time, updated_time, name, kcal, carb_g, protein_g, fat_g,
                            Macro_ratio_c, Macro_ratio_p, Macro_ratio_f)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            [
                                t,
                                t,
                                name,
                                kcal,
                                carb_g,
                                protein_g,
                                fat_g,
                                mr_c,
                                mr_p,
                                mr_f,
                            ],
                        )
                        cursor.execute("SELECT LAST_INSERT_ID()")
                        food_id = int(cursor.fetchone()[0])

                    new_food_ids.append(food_id)

                # 2) TH 합계 계산(바로 cleaned로 계산)
                total_kcal = sum(x[1] for x in cleaned)
                total_carb = sum(x[2] for x in cleaned)
                total_prot = sum(x[3] for x in cleaned)
                total_fat = sum(x[4] for x in cleaned)

                # 3) CUS_FOOD_TH upsert
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

                # 4) CUS_FOOD_TS 덮어쓰기 (DELETE → INSERT)
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

        # ✅ 저장 완료 후 “검색창 있는 식단기록 첫 페이지”로 이동시키기 위한 URL 반환
        # 너 프로젝트에서 첫 페이지가 /record/meal/ 이면 그대로 두면 됨
        return JsonResponse(
            {
                "ok": True,
                "th_action": th_action,
                "deleted_ts": deleted_ts,
                "inserted_ts": len(cleaned),
                "cust_id": cust_id,
                "rgs_dt": rgs_dt,
                "seq": seq,
                "time_slot": time_slot,
                "redirect_url": "/record/meal/",
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
        cust_id = getattr(request.user, "cust_id", None) or request.session.get("cust_id")
        if not cust_id:
            return JsonResponse({"ok": False, "error": "CUST_ID_REQUIRED"}, status=400)

        # context
        rgs_dt = (request.POST.get("rgs_dt") or request.session.get("rgs_dt") or "").strip()
        time_slot = (request.POST.get("time_slot") or request.session.get("time_slot") or "").strip()
        seq_raw = request.POST.get("seq") or request.session.get("seq") or "1"

        try:
            seq = int(seq_raw)
        except Exception:
            return JsonResponse({"ok": False, "error": "SEQ_INVALID"}, status=400)

        if not rgs_dt or not time_slot:
            return JsonResponse(
                {"ok": False, "error": "CTX_REQUIRED",
                 "detail": {"rgs_dt": rgs_dt, "time_slot": time_slot}},
                status=400,
            )

        # bucket
        bucket = (os.getenv("AWS_S3_BUCKET") or "").strip()
        if not bucket:
            return JsonResponse({"ok": False, "error": "AWS_S3_BUCKET_MISSING"}, status=400)

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
