# ml/menu_reco/db_repo.py
from __future__ import annotations

from typing import Dict, Any, List, Tuple, Optional
from django.db import connection, transaction

def _fetchone_dict(sql: str, params: List[Any]) -> Optional[Dict[str, Any]]:
    with connection.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))

def _fetchall_dict(sql: str, params: List[Any]) -> List[Dict[str, Any]]:
    with connection.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in rows]

# 1) 프로필
def get_profile(cust_id: str) -> Optional[Dict[str, Any]]:
    # ✅ 너 DB의 CUS_PROFILE_TS 컬럼명에 맞춰서 SELECT를 확정해야 함
    # (예시) purpose, Recommended_calories, Ratio_carb, Ratio_protein, Ratio_fat
    sql = """
    SELECT
        cust_id,
        purpose,
        Recommended_calories,
        Ratio_carb,
        Ratio_protein,
        Ratio_fat
    FROM CUS_PROFILE_TS
    WHERE cust_id = %s
    ORDER BY updated_time DESC
    LIMIT 1
    """
    return _fetchone_dict(sql, [cust_id])

# 2) 오늘 섭취 합계(CUS_FOOD_TH 기반)
def get_day_eaten_sum(cust_id: str, rgs_dt: str) -> Dict[str, Any]:
    sql = """
    SELECT
        COALESCE(SUM(kcal), 0)      AS sum_kcal,
        COALESCE(SUM(carb_g), 0)    AS sum_carb_g,
        COALESCE(SUM(protein_g), 0) AS sum_protein_g,
        COALESCE(SUM(fat_g), 0)     AS sum_fat_g
    FROM CUS_FOOD_TH
    WHERE cust_id=%s AND rgs_dt=%s
    """
    return _fetchone_dict(sql, [cust_id, rgs_dt]) or {"sum_kcal": 0, "sum_carb_g": 0, "sum_protein_g": 0, "sum_fat_g": 0}

# 3) 최근 n일 macro 합(CUS_FOOD_TH 기반)
def get_recent_macro_sum(cust_id: str, days: int = 7) -> Dict[str, Any]:
    # rgs_dt가 YYYYMMDD 문자열이므로 날짜함수 적용이 어렵다면 그냥 최근 N일 기준을 python에서 계산해 넣는 게 더 안전.
    # 여기서는 MySQL STR_TO_DATE를 사용(형식이 항상 YYYYMMDD라는 전제)
    sql = f"""
    SELECT
        COALESCE(SUM(kcal), 0)      AS sum_kcal,
        COALESCE(SUM(carb_g), 0)    AS sum_carb_g,
        COALESCE(SUM(protein_g), 0) AS sum_protein_g,
        COALESCE(SUM(fat_g), 0)     AS sum_fat_g
    FROM CUS_FOOD_TH
    WHERE cust_id=%s
      AND STR_TO_DATE(rgs_dt, '%%Y%%m%%d') >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
    """
    return _fetchone_dict(sql, [cust_id, int(days)]) or {"sum_kcal": 0, "sum_carb_g": 0, "sum_protein_g": 0, "sum_fat_g": 0}

# 4) Food name -> id 매핑
def map_food_names_to_ids(food_names: List[str]) -> Dict[str, int]:
    food_names = [str(x).strip() for x in (food_names or []) if str(x).strip()]
    if not food_names:
        return {}

    in_ph = ",".join(["%s"] * len(food_names))
    sql = f"""
    SELECT name, food_id
    FROM FOOD_TB
    WHERE name IN ({in_ph})
    """
    rows = _fetchall_dict(sql, food_names)
    out: Dict[str, int] = {}
    for r in rows:
        nm = str(r["name"])
        out[nm] = int(r["food_id"])
    return out

# 5) MENU_RECOM_TH upsert
def upsert_menu_recom_rows(
    *, cust_id: str, rgs_dt: str, rec_time_slot: str, rows: List[Tuple[str, str]]
) -> None:
    """
    rows: List[(rec_type, food_id)]
      - rec_type: P/H/E
      - food_id: str/int
    MENU_RECOM_TH 컬럼(이미지 기준): cust_id, rgs_dt, rec_time_slot, rec_type, food_id (+ created_time/updated_time)
    """
    if not rows:
        return

    sql = """
    INSERT INTO MENU_RECOM_TH
      (created_time, updated_time, cust_id, rgs_dt, rec_time_slot, rec_type, food_id)
    VALUES
      (DATE_FORMAT(NOW(),'%%Y%%m%%d%%H%%i%%s'),
       DATE_FORMAT(NOW(),'%%Y%%m%%d%%H%%i%%s'),
       %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
       updated_time = VALUES(updated_time),
       food_id      = VALUES(food_id)
    """
    with transaction.atomic(), connection.cursor() as cur:
        for rec_type, food_id in rows:
            cur.execute(sql, [cust_id, rgs_dt, rec_time_slot, rec_type, str(food_id)])