# ml/lstm/batch.py
from __future__ import annotations

import traceback
from datetime import datetime, time, date
from typing import Any, Dict, List, Tuple

from django.db import connection
from django.utils import timezone

from ml.lstm.prediction_service import run_prediction_for_date
from ml.lstm.predictor import _pick_source_slot_DLM


def _today_yyyymmdd() -> str:
    return timezone.localdate().strftime("%Y%m%d")


def _is_after_8pm() -> bool:
    # 서버 기준(naive) 대신 Django timezone.localtime을 사용
    now = timezone.localtime().time()
    return now >= time(20, 0)


def _get_cust_ids_with_any_ts_on_date(rgs_dt: str) -> List[str]:
    """
    배치 대상: 오늘 TS(키워드)가 있는 사용자들
    (Gate도 키워드를 보므로, 최소 조건으로 TS 존재를 사용)
    """
    sql = """
        SELECT DISTINCT cust_id
        FROM CUS_FEEL_TS
        WHERE rgs_dt = %s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [rgs_dt])
        return [str(r[0]) for r in cursor.fetchall() if r and r[0]]


def run_8pm_batch_prediction(force: bool = False) -> Dict[str, Any]:
    """
    20:00 배치(백업):
    - 원칙: 기록 저장 이벤트 훅이 이미 예측을 생성한다.
    - 그래도 혹시 누락되었거나, 특정 사용자에 대해 예측이 비어있을 수 있으니 20:00에 한번 더 보장.
    - 정책: '오늘 rgs_dt'에서 source는 D>L>M, 그걸로 target 생성.
    - 배치는 보통 skip_if_exists=True(이미 있으면 건너뜀) 권장.
    """
    if not force and not _is_after_8pm():
        return {"ok": False, "reason": "before_20:00", "now": timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")}

    today = _today_yyyymmdd()
    cust_ids = _get_cust_ids_with_any_ts_on_date(today)

    print("[BATCHDBG][ENTER]", "today=", today, "cust_cnt=", len(cust_ids), "force=", force, flush=True)

    results = []
    ok_cnt = 0
    skip_cnt = 0
    fail_cnt = 0

    for cust_id in cust_ids:
        try:
            picked = _pick_source_slot_DLM(cust_id, today)
            if not picked:
                results.append({"cust_id": cust_id, "ok": False, "reason": "no_source_today"})
                fail_cnt += 1
                continue

            source_slot, source_seq = picked

            r = run_prediction_for_date(
                cust_id=cust_id,
                source_date=today,
                source_slot=source_slot,
                source_seq=int(source_seq),
                skip_if_exists=True,  # 배치는 보통 스킵
            )

            results.append({"cust_id": cust_id, **r})

            if r.get("ok") and r.get("skipped"):
                skip_cnt += 1
            elif r.get("ok"):
                ok_cnt += 1
            else:
                fail_cnt += 1

        except Exception as e:
            fail_cnt += 1
            results.append({"cust_id": cust_id, "ok": False, "reason": f"batch_exception: {e}", "trace": traceback.format_exc()})

    summary = {
        "ok": True,
        "today": today,
        "total": len(cust_ids),
        "ok_cnt": ok_cnt,
        "skip_cnt": skip_cnt,
        "fail_cnt": fail_cnt,
        "results": results,
    }
    print("[BATCHDBG][EXIT]", summary, flush=True)
    return summary
