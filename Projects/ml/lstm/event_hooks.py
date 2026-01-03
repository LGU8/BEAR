# ml/lstm/event_hooks.py
from __future__ import annotations

from datetime import date
from typing import Optional

from ml.lstm.prediction_service import upsert_next_morning_negative_prediction


def on_dinner_record_saved(
    *,
    cust_id: str,
    asof_yyyymmdd: Optional[str] = None,
    is_late: bool = False,     # 20:00 이후 늦게 기록이면 True로 넣어도 되고 안 넣어도 됨(메타용)
    is_update: bool = False,   # 기존 저녁 기록 수정이면 True(메타용)
) -> dict:
    """
    저녁 기록 저장(신규/수정) 시점에서 호출:
    - 무조건 재예측(=skip_if_exists=False)
    - 기존 내일M row가 있으면 UPDATE로 덮어씀 + updated_time 갱신
    """
    if asof_yyyymmdd is None:
        asof_yyyymmdd = date.today().strftime("%Y%m%d")

    # source 메타만 구분 (원하면 detail_json에 더 남길 수 있음)
    if is_update:
        source = "dinner_update"
    elif is_late:
        source = "dinner_late"
    else:
        source = "dinner_event"

    return upsert_next_morning_negative_prediction(
        cust_id=cust_id,
        asof_yyyymmdd=asof_yyyymmdd,
        source=source,
        skip_if_exists=False,  # ✅ 이벤트는 무조건 재예측/갱신
    )
