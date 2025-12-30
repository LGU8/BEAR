from __future__ import annotations

from typing import Dict, Any, Optional, List, Set
from django.db import connection
from datetime import datetime, timedelta

from .repo import resolve_date_col

def _to_date_str(value: str) -> Optional[str]:
    """
    value가
    - YYYYMMDDHHMMSS -> YYYYMMDD
    - YYYYMMDD -> YYYYMMDD
    - 그 외 -> 파싱 시도
    """
    s = (value or "").strip()
    if not s:
        return None

    digits = "".join(ch for ch in s if ch.isdigit())

    if len(digits) >= 8:
        return digits[:8]

    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d.strftime("%Y%m%d")
    except Exception:
        return None

def count_rows(table: str, cust_id: str, filters: Dict[str, Any], field_exists: Optional[str] = None) -> int:
    where = ["cust_id=%s"]
    params = [cust_id]
    for k, v in (filters or {}).items():
        where.append(f"{k}=%s")
        params.append(v)
    if field_exists:
        where.append(f"{field_exists} IS NOT NULL")
    sql = f"SELECT COUNT(*) FROM {table} WHERE " + " AND ".join(where)
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return int(cur.fetchone()[0])

def distinct_days(table: str, cust_id: str, filters: Dict[str, Any]) -> int:
    date_col = resolve_date_col(table)
    where = ["cust_id=%s"]
    params = [cust_id]
    for k, v in (filters or {}).items():
        where.append(f"{k}=%s")
        params.append(v)

    # date_col이 time(14)일 수도 있어서 LEFT(date_col,8)로 distinct
    sql = f"""
    SELECT COUNT(DISTINCT LEFT({date_col}, 8))
    FROM {table}
    WHERE {" AND ".join(where)}
    """
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return int(cur.fetchone()[0])

def fetch_distinct_day_set(table: str, cust_id: str, filters: Dict[str, Any]) -> Set[str]:
    date_col = resolve_date_col(table)
    where = ["cust_id=%s"]
    params = [cust_id]
    for k, v in (filters or {}).items():
        where.append(f"{k}=%s")
        params.append(v)

    sql = f"""
    SELECT DISTINCT LEFT({date_col}, 8) AS ymd
    FROM {table}
    WHERE {" AND ".join(where)}
    """
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return {str(r[0]) for r in cur.fetchall() if r and r[0]}

def streak_days(table: str, cust_id: str, filters: Dict[str, Any], need: int) -> bool:
    """
    table에서 조건 만족한 날짜들이 need일 '연속'이면 True
    """
    days = fetch_distinct_day_set(table, cust_id, filters)
    if not days:
        return False

    # 기준: 가장 최신 날짜부터 역으로 연속 체크
    # 최신 날짜를 max로 잡고, 그 날짜부터 need일 연속 존재하면 True
    latest = max(days)
    try:
        cur = datetime.strptime(latest, "%Y%m%d")
    except Exception:
        return False

    for i in range(need):
        d = (cur - timedelta(days=i)).strftime("%Y%m%d")
        if d not in days:
            return False
    return True

def days_with_min_rows(table: str, cust_id: str, filters: Dict[str, Any], min_rows_per_day: int) -> int:
    """
    하루에 최소 N행 이상 기록한 '날짜' 수
    (E000000022 같은: 하루 3회 이상 기록한 날이 5번)
    """
    date_col = resolve_date_col(table)
    where = ["cust_id=%s"]
    params = [cust_id]
    for k, v in (filters or {}).items():
        where.append(f"{k}=%s")
        params.append(v)

    sql = f"""
    SELECT COUNT(*)
    FROM (
      SELECT LEFT({date_col}, 8) AS ymd, COUNT(*) AS cnt
      FROM {table}
      WHERE {" AND ".join(where)}
      GROUP BY LEFT({date_col}, 8)
      HAVING COUNT(*) >= %s
    ) t
    """
    params2 = params + [min_rows_per_day]
    with connection.cursor() as cur:
        cur.execute(sql, params2)
        return int(cur.fetchone()[0])

def days_with_min_slots(table: str, cust_id: str, filters: Dict[str, Any], min_distinct_slots_per_day: int) -> int:
    """
    하루에 distinct time_slot 개수가 N 이상인 '날짜' 수
    (F000000028~034)
    """
    date_col = resolve_date_col(table)
    where = ["cust_id=%s"]
    params = [cust_id]
    for k, v in (filters or {}).items():
        where.append(f"{k}=%s")
        params.append(v)

    sql = f"""
    SELECT COUNT(*)
    FROM (
      SELECT LEFT({date_col}, 8) AS ymd, COUNT(DISTINCT time_slot) AS slot_cnt
      FROM {table}
      WHERE {" AND ".join(where)}
      GROUP BY LEFT({date_col}, 8)
      HAVING COUNT(DISTINCT time_slot) >= %s
    ) t
    """
    params2 = params + [min_distinct_slots_per_day]
    with connection.cursor() as cur:
        cur.execute(sql, params2)
        return int(cur.fetchone()[0])

def count_join_source_type(cust_id: str, source_type: str) -> int:
    """
    CUS_FOOD_TS x FOOD_TB join으로 source_type=ocr/barcode/manual count
    (F000000039~041)
    """
    sql = """
    SELECT COUNT(*)
    FROM CUS_FOOD_TS t
    JOIN FOOD_TB f ON t.food_id = f.food_id
    WHERE t.cust_id=%s AND f.source_type=%s
    """
    with connection.cursor() as cur:
        cur.execute(sql, [cust_id, source_type])
        return int(cur.fetchone()[0])