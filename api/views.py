# api/views.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import connection, transaction

from ml.menu_reco.service import recommend_and_commit


# -----------------------
# DB helpers
# -----------------------
def _fetch_menu_recom_with_food_name(
    *,
    cust_id: str,
    rgs_dt: str,
    rec_time_slot: str,
) -> List[Dict[str, Any]]:
    """
    MENU_RECOM_TH + FOOD_TB 조인해서 food_name 포함 조회
    MENU_RECOM_TH 컬럼: rec_time_slot (주의: time_slot 아님)
    FOOD_TB 컬럼: name (현재 모델 FoodTb.name)
    """
    sql = """
        SELECT
            m.cust_id,
            m.rgs_dt,
            m.rec_time_slot,
            m.rec_type,
            m.food_id,
            f.name AS food_name,
            m.updated_time
        FROM MENU_RECOM_TH m
        LEFT JOIN FOOD_TB f
          ON f.food_id = m.food_id
        WHERE m.cust_id = %s
          AND m.rgs_dt = %s
          AND m.rec_time_slot = %s
        ORDER BY m.rec_type
    """
    with connection.cursor() as cur:
        cur.execute(sql, [cust_id, rgs_dt, rec_time_slot])
        rows = cur.fetchall()

    items: List[Dict[str, Any]] = []
    for (cust_id_, rgs_dt_, slot_, rec_type, food_id, food_name, updated_time) in rows:
        items.append(
            {
                "rec_type": rec_type,                 # P/H/E
                "food_id": str(food_id) if food_id is not None else None,
                "food_name": food_name,               # FOOD_TB.name 조인 결과
                "updated_time": updated_time,
            }
        )
    return items


def _json_body(request: HttpRequest) -> Dict[str, Any]:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except Exception:
        return {}


def _bad_request(msg: str) -> JsonResponse:
    return JsonResponse({"ok": False, "error": msg}, status=400)


def _server_error(msg: str) -> JsonResponse:
    return JsonResponse({"ok": False, "error": msg}, status=500)


# -----------------------
# POST /api/menu/recommend
# -----------------------
@csrf_exempt
@require_http_methods(["POST"])
def menu_recommend_post(request: HttpRequest) -> JsonResponse:
    body = _json_body(request)

    cust_id = str(body.get("cust_id") or "").strip()
    mood = str(body.get("mood") or "").strip().lower()          # pos/neu/neg
    energy = str(body.get("energy") or "").strip().lower()      # low/med/hig
    rgs_dt = str(body.get("rgs_dt") or "").strip()              # YYYYMMDD
    rec_time_slot = str(body.get("rec_time_slot") or "").strip().upper()  # M/L/D

    current_food = body.get("current_food")
    recent_foods = body.get("recent_foods")

    # ---- validations (필수)
    if not cust_id:
        return _bad_request("cust_id is required")
    if mood not in {"pos", "neu", "neg"}:
        return _bad_request("mood must be one of: pos/neu/neg")
    if energy not in {"low", "med", "hig"}:
        return _bad_request("energy must be one of: low/med/hig")
    if len(rgs_dt) != 8 or not rgs_dt.isdigit():
        return _bad_request("rgs_dt must be YYYYMMDD")
    if rec_time_slot not in {"M", "L", "D"}:
        return _bad_request("rec_time_slot must be one of: M/L/D")

    if current_food is not None and not isinstance(current_food, str):
        return _bad_request("current_food must be string or null")

    if recent_foods is not None:
        if not isinstance(recent_foods, list) or not all(isinstance(x, str) for x in recent_foods):
            return _bad_request("recent_foods must be list[str] or null")

    # ---- execute
    try:
        # DB upsert까지 포함되므로 트랜잭션으로 묶어도 OK
        with transaction.atomic():
            df = recommend_and_commit(
                cust_id=cust_id,
                mood=mood,
                energy=energy,
                rgs_dt=rgs_dt,
                rec_time_slot=rec_time_slot,
                current_food=current_food,
                recent_foods=recent_foods,
            )

        # 권장: 응답은 “저장된 확정본”을 DB에서 다시 읽어서 내려주기
        items = _fetch_menu_recom_with_food_name(
            cust_id=cust_id,
            rgs_dt=rgs_dt,
            rec_time_slot=rec_time_slot,
        )

        # 디버그/부가 정보(선택): service가 준 score도 같이 내려주고 싶으면
        # DF에서 rec_type별 score_phase3 매핑해서 items에 붙일 수 있음
        score_map: Dict[str, float] = {}
        if df is not None and not df.empty and "rec_type" in df.columns and "score_phase3" in df.columns:
            for _, r in df.iterrows():
                rt = str(r.get("rec_type") or "")
                # DF의 rec_type은 "선호형..." 같은 문자열일 수 있으니,
                # MENU_RECOM_TH 저장 코드(P/H/E) 기준으로 정리하려면 df에 저장코드 컬럼을 추가하는 게 베스트.
                # 여기서는 안전하게 스킵(필요하면 내가 바로 개선해줄게).
                _ = rt

        return JsonResponse(
            {
                "ok": True,
                "cust_id": cust_id,
                "rgs_dt": rgs_dt,
                "rec_time_slot": rec_time_slot,
                "items": items,
            },
            status=200,
        )

    except ValueError as e:
        # profile 누락 등 예측 가능한 오류
        return _bad_request(str(e))
    except Exception as e:
        return _server_error(f"{type(e).__name__}: {e}")


# -----------------------
# GET /api/menu/recommend?cust_id=...&rgs_dt=...&rec_time_slot=...
# -----------------------
@require_http_methods(["GET"])
def menu_recommend_get(request: HttpRequest) -> JsonResponse:
    cust_id = str(request.GET.get("cust_id") or "").strip()
    rgs_dt = str(request.GET.get("rgs_dt") or "").strip()
    rec_time_slot = str(request.GET.get("rec_time_slot") or "").strip().upper()

    if not cust_id:
        return _bad_request("cust_id is required")
    if len(rgs_dt) != 8 or not rgs_dt.isdigit():
        return _bad_request("rgs_dt must be YYYYMMDD")
    if rec_time_slot not in {"M", "L", "D"}:
        return _bad_request("rec_time_slot must be one of: M/L/D")

    try:
        items = _fetch_menu_recom_with_food_name(
            cust_id=cust_id,
            rgs_dt=rgs_dt,
            rec_time_slot=rec_time_slot,
        )
        return JsonResponse(
            {
                "ok": True,
                "cust_id": cust_id,
                "rgs_dt": rgs_dt,
                "rec_time_slot": rec_time_slot,
                "items": items,
            },
            status=200,
        )
    except Exception as e:
        return _server_error(f"{type(e).__name__}: {e}")