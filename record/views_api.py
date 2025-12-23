# record/views_api.py
import uuid
import json
import tempfile
from pathlib import Path
from datetime import datetime

from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.db import connection, transaction
from django.db.models import Value
from django.db.models.functions import Coalesce

from .services.barcode.total import run_barcode_pipeline
from .services.barcode.mapping_code import EnvNotSetError, UpstreamAPIError

from .models import FoodTb

# 감정 기록 키워드 api
def keyword_api(request):
    """
    감정(mood) + 활성도(energy)에 따라
    키워드 목록을 DB에서 조회해서 JSON으로 반환
    """

    if request.method != "GET":
        return JsonResponse(
            {"error": "GET method only"},
            status=405
        )

    # 파라미터 받기
    mood = request.GET.get("mood")
    energy = request.GET.get("energy")

    if not mood or not energy:
        return JsonResponse(
            {"error": "mood and energy are required"},
            status=400
        )

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

def _normalize_candidate(raw: dict) -> dict:
    """
    mapping_code.get_product_info_by_barcode() 결과(C005) → 프론트/commit 공통 규격으로 정규화
    """
    return {
        "candidate_id": (raw.get("candidate_id") or "").strip(),
        "name": (raw.get("product_name") or "").strip(),
        "brand": (raw.get("manufacturer") or "").strip(),
        "flavor": "",  # C005에는 flavor가 보통 없음 (있으면 채워도 됨)
        "report_no": (raw.get("report_no") or "").strip(),
        "barcode": (raw.get("barcode") or "").strip(),
        "raw": raw.get("raw") if isinstance(raw.get("raw"), dict) else raw,
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
            "name": c["name"],
            "brand": c["brand"],
            "flavor": c["flavor"],
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
            "name": c["name"],
            "brand": c["brand"],
            "flavor": c["flavor"],
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
    candidate_id = (request.POST.get("candidate_id") or "").strip()

    if not draft_id or not candidate_id:
        try:
            body = json.loads((request.body or b"{}").decode("utf-8"))
            draft_id = draft_id or str(body.get("draft_id", "")).strip()
            candidate_id = candidate_id or str(body.get("candidate_id", "")).strip()
        except Exception:
            pass

    if not draft_id or not candidate_id:
        return JsonResponse(
            {
                "ok": False,
                "error": "BAD_REQUEST",
                "message": "draft_id와 candidate_id가 필요합니다.",
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
    picked = next(
        (
            c
            for c in candidates
            if str(c.get("candidate_id", "")).strip() == candidate_id
        ),
        None,
    )
    if not picked:
        return JsonResponse(
            {
                "ok": False,
                "error": "CANDIDATE_NOT_FOUND",
                "message": "candidate not found",
            },
            status=404,
        )

    # ✅ 1) DB 저장 먼저 (실패 시 draft 유지)
    try:
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

    # ✅ 2) 저장 성공 후 draft 제거
    request.session.pop(session_key, None)
    request.session.modified = True

    return JsonResponse(
        {
            "ok": True,
            "date": data.get("date"),
            "meal": data.get("meal"),
            "barcode": data.get("barcode"),
            "picked": {
                "candidate_id": picked.get("candidate_id", ""),
                "name": picked.get("name", ""),
                "brand": picked.get("brand", ""),
                "flavor": picked.get("flavor", ""),
            },
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
