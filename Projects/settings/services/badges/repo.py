from __future__ import annotations

from typing import Dict, Any, List, Set, Optional
from django.db import connection, transaction
from datetime import datetime
import json

def now_yyyymmddhhmmss() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")

def get_owned_badge_ids(cust_id: str) -> Set[str]:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT badge_id FROM CUS_BADGE_TM WHERE cust_id=%s",
            [cust_id],
        )
        return {str(r[0]) for r in cur.fetchall()}

@transaction.atomic
def insert_badge_if_not_exists(cust_id: str, badge_id: str, acquired_time: Optional[str] = None) -> bool:
    """
    idempotent insert
    return True if inserted, False if already exists
    """
    acquired_time = acquired_time or now_yyyymmddhhmmss()
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO CUS_BADGE_TM (cust_id, badge_id, acquired_time, created_time, updated_time)
            SELECT %s, %s, %s, %s, %s
            FROM DUAL
            WHERE NOT EXISTS (
              SELECT 1 FROM CUS_BADGE_TM WHERE cust_id=%s AND badge_id=%s
            )
            """,
            [cust_id, badge_id, acquired_time, acquired_time, acquired_time, cust_id, badge_id],
        )
        return cur.rowcount == 1

def list_table_columns(table_name: str, schema_name: Optional[str] = None) -> List[str]:
    """
    현재 연결된 DB schema에서 table columns 조회
    """
    with connection.cursor() as cur:
        cur.execute("SELECT DATABASE()")
        db = schema_name or cur.fetchone()[0]

        cur.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
            """,
            [db, table_name],
        )
        return [str(r[0]) for r in cur.fetchall()]

def resolve_date_col(table_name: str) -> str:
    """
    streak/days_threshold 평가를 위한 날짜 컬럼 자동 탐색.
    - 프로젝트마다 컬럼명이 달라서 '확정' 정보가 없으므로 자동 탐색으로 안전하게 처리.
    """
    cols = set([c.lower() for c in list_table_columns(table_name)])
    candidates = [
        "rgs_dt", "reg_dt", "record_dt",
        "created_dt",
        "created_time", "event_time", "login_time",
        "rgs_time",
        "ymd", "date",
    ]
    for c in candidates:
        if c.lower() in cols:
            return c
    # fallback: created_time 유사 탐색
    for c in cols:
        if "date" in c or c.endswith("_dt"):
            return c
    for c in cols:
        if "time" in c:
            return c
    raise RuntimeError(f"[BadgeEngine] 날짜 컬럼을 찾을 수 없음: table={table_name}, cols={sorted(cols)}")

def fetch_event_count(cust_id: str, event_key: str) -> int:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM BADGE_EVENT_TH
            WHERE cust_id=%s AND event_key=%s
            """,
            [cust_id, event_key],
        )
        return int(cur.fetchone()[0])

def insert_event(cust_id: str, event_key: str, meta: Optional[Dict[str, Any]] = None, event_time: Optional[str] = None) -> None:
    t = event_time or now_yyyymmddhhmmss()
    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO BADGE_EVENT_TH (cust_id, event_key, event_time, meta_json, created_time)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [cust_id, event_key, t, meta_json, t],
        )