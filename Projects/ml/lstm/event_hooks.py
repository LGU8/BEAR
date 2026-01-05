from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Tuple

from django.db import connection
from django.utils import timezone

from ml.lstm.prediction_service import run_prediction_for_date
from ml.behavior_llm.behavior_service import generate_and_save_behavior_recom


# =========================
# source 선택 로직 (event 전용)
# =========================
def _exists_slot(cust_id: str, rgs_dt: str, slot: str) -> bool:
    sql = """
        SELECT 1
        FROM CUS_FEEL_TH
        WHERE cust_id = %s AND rgs_dt = %s AND time_slot = %s
        LIMIT 1
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [cust_id, rgs_dt, slot])
        return cursor.fetchone() is not None


def _pick_source_slot_for_date(cust_id: str, rgs_dt: str) -> Optional[str]:
    """
    같은 날짜 내 source_slot 우선순위: D > L > M
    """
    if _exists_slot(cust_id, rgs_dt, "D"):
        return "D"
    if _exists_slot(cust_id, rgs_dt, "L"):
        return "L"
    if _exists_slot(cust_id, rgs_dt, "M"):
        return "M"
    return None


def _latest_seq_for_slot(cust_id: str, rgs_dt: str, slot: str) -> Optional[int]:
    sql = """
        SELECT MAX(seq)
        FROM CUS_FEEL_TH
        WHERE cust_id = %s AND rgs_dt = %s AND time_slot = %s
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [cust_id, rgs_dt, slot])
        row = cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else None


def pick_source_for_event(
    cust_id: str,
    rgs_dt: str,
    time_slot: str,
    seq: int,
) -> Tuple[str, str, int]:
    """
    이벤트 발생 시 source 결정:
    - source_date = rgs_dt
    - source_slot = D > L > M
    - source_seq = 해당 slot의 최신 seq
    """
    source_date = rgs_dt
    source_slot = _pick_source_slot_for_date(cust_id, rgs_dt)

    if source_slot is None:
        source_slot = time_slot.upper()

    source_seq = _latest_seq_for_slot(cust_id, rgs_dt, source_slot)
    if source_seq is None:
        source_seq = int(seq)

    return source_date, source_slot, source_seq


# =========================
# target 전이 로직 (여기에 정의!)
# =========================
def target_from_source(source_date: str, source_slot: str) -> Tuple[str, str]:
    """
    슬롯 전이 규칙 (고정):
    - M -> L (같은 날)
    - L -> D (같은 날)
    - D -> 다음 날 M
    """
    s = source_slot.upper()

    if s == "M":
        return source_date, "L"
    if s == "L":
        return source_date, "D"

    d = datetime.strptime(source_date, "%Y%m%d").date()
    next_ymd = (d + timedelta(days=1)).strftime("%Y%m%d")
    return next_ymd, "M"


# =========================
# event hook (핵심)
# =========================
def on_mood_recorded(
    cust_id: str,
    rgs_dt: str,
    time_slot: str,
    seq: int,
    is_late: bool = False,
) -> bool:
    now_str = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")

    print(
        "[EVTDBG][ENTER]",
        cust_id,
        rgs_dt,
        time_slot,
        seq,
        now_str,
        flush=True,
    )

    try:
        # 1) source 선택
        source_date, source_slot, source_seq = pick_source_for_event(
            cust_id, rgs_dt, time_slot, seq
        )

        print(
            "[EVTDBG][SOURCE]",
            cust_id,
            source_date,
            source_slot,
            source_seq,
            flush=True,
        )

        # 2) target 계산
        target_date, target_slot = target_from_source(source_date, source_slot)

        # 3) 예측 + 저장
        ok = run_prediction_for_date(
            cust_id=cust_id,
            source_date=source_date,
            source_slot=source_slot,
            source_seq=source_seq,
            target_date=target_date,
            target_slot=target_slot,
            skip_if_exists=False,
        )

        print(
            "[EVTDBG][PRED]",
            cust_id,
            target_date,
            target_slot,
            ok,
            flush=True,
        )

        if not ok:
            return False

        # 4) 행동추천 (예측이 있으면 무조건)
        beh_ok = generate_and_save_behavior_recom(
            cust_id=cust_id,
            target_date=target_date,
            target_slot=target_slot,
            reason="after_pred",
        )
        print("[EVTDBG][BEH_CALL]", cust_id, target_date, target_slot, flush=True)

        msg = generate_and_save_behavior_recom(
            cust_id=cust_id,
            target_date=target_date,
            target_slot=target_slot,
        )

        print("[EVTDBG][BEH_DONE]", "len=", len(msg or ""), flush=True)

        print(
            "[EVTDBG][BEH]",
            cust_id,
            target_date,
            target_slot,
            beh_ok,
            flush=True,
        )

        return True

    except Exception as e:
        print("[EVTDBG][EXC]", repr(e), flush=True)
        return False
