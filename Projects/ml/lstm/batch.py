# ml/lstm/batch.py
from __future__ import annotations

from datetime import date, datetime, time
from typing import List

from django.db import connection

from ml.lstm.prediction_service import upsert_next_morning_negative_prediction


def _today_yyyymmdd() -> str:
    return date.today().strftime("%Y%m%d")


def _is_after_8pm() -> bool:
    return datetime.now().time() >= time(20, 0)


def _fetch_cust_ids_with_today_ts(today_yyyymmdd: str) -> List[str]:
    """
    정책: 오늘 날짜(rgs_dt=오늘)에 CUS_FEEL_TS가 1건 이상 존재하는 사용자만 배치 대상
    (아침/점심만 있어도 OK — 날짜만 오늘이면 OK)
    """
    sql = """
        SELECT DISTINCT cust_id
        FROM CUS_FEEL_TS
        WHERE rgs_dt = %s
    """
    with connection.cursor() as cur:
        cur.execute(sql, [today_yyyymmdd])
        return [str(r[0]) for r in cur.fetchall() if r and r[0]]


def run_batch_predict_next_morning_if_needed() -> dict:
    """
    report와 동일한 기준(naive date/datetime)으로 20:00 이후에만 실행되도록 보호.
    - 실제 스케줄러가 20:00에 호출하더라도,
      혹시 다른 시간에 호출되는 걸 방지하기 위한 방어 로직임.
    """
    today = _today_yyyymmdd()

    if not _is_after_8pm():
        return {
            "ran": False,
            "today": today,
            "reason": "before_20:00",
            "processed": 0,
            "skipped": 0,
        }

    cust_ids = _fetch_cust_ids_with_today_ts(today)

    processed = 0
    skipped = 0
    for cust_id in cust_ids:
        res = upsert_next_morning_negative_prediction(
            cust_id=cust_id,
            asof_yyyymmdd=today,
            source="batch_20",
            skip_if_exists=True,  # ✅ 운영 안전: 이미 내일M row 있으면 스킵
        )
        if res.get("skipped"):
            skipped += 1
        else:
            processed += 1

    return {
        "ran": True,
        "today": today,
        "reason": "after_20:00",
        "candidates": len(cust_ids),
        "processed": processed,
        "skipped": skipped,
    }
