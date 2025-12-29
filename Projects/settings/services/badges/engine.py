from __future__ import annotations

from typing import Dict, Any, List, Optional
from datetime import datetime

from .loader import load_badge_meta, iter_items
from .repo import get_owned_badge_ids, insert_badge_if_not_exists, fetch_event_count
from .evaluators import (
    count_rows,
    distinct_days,
    streak_days,
    days_with_min_rows,
    days_with_min_slots,
    count_join_source_type,
)

def now_yyyymmddhhmmss() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")

def award_badges(
    cust_id: str,
    trigger_event: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    badge_meta.json 전체 규칙을 평가하여, 만족하는 뱃지를 CUS_BADGE_TM에 넣는다.
    return: 이번 호출로 새로 지급된 badge_id list
    """
    context = context or {}
    meta = load_badge_meta()
    items = iter_items(meta)

    owned = get_owned_badge_ids(cust_id)
    granted: List[str] = []

    for it in items:
        badge_id = str(it.get("badge_id", "")).strip()
        if not badge_id or badge_id in owned:
            continue

        unlock_type = (it.get("unlock_type") or "").strip()
        rule = it.get("unlock_rule") or {}
        ok = False

        # --------------------
        # 1) login
        # --------------------
        if unlock_type == "login":
            event = rule.get("event")
            if trigger_event == event:
                ok = True

        # --------------------
        # 2) count
        # --------------------
        elif unlock_type == "count":
            table = rule.get("table")
            filters = rule.get("filters", {})
            need = int(rule.get("count", 0))
            field_exists = rule.get("field_exists")
            cur = count_rows(table, cust_id, filters, field_exists=field_exists)
            ok = (cur >= need)

        # --------------------
        # 3) daily_combo (distinct_days)
        # --------------------
        elif unlock_type == "daily_combo":
            table = rule.get("table")
            filters = rule.get("filters", {})
            need_days = int(rule.get("days_count", 0))
            cur_days = distinct_days(table, cust_id, filters)
            ok = (cur_days >= need_days)

        # --------------------
        # 4) streak
        # --------------------
        elif unlock_type == "streak":
            table = rule.get("table")
            filters = rule.get("filters", {})
            need = int(rule.get("streak_days", 0))
            ok = streak_days(table, cust_id, filters, need)

        # --------------------
        # 5) days_threshold
        #   - days_with_min_rows
        #   - days_with_min_slots
        # --------------------
        elif unlock_type == "days_threshold":
            table = rule.get("table")
            metric = rule.get("metric")

            filters = rule.get("filters", {})

            need_days = int(rule.get("days_count", 0))

            if metric == "days_with_min_rows":
                min_rows = int(rule.get("min_rows_per_day", 0))
                cur = days_with_min_rows(table, cust_id, filters, min_rows_per_day=min_rows)
                ok = (cur >= need_days)

            elif metric == "days_with_min_slots":
                min_slots = int(rule.get("min_distinct_slots_per_day", 0))
                cur = days_with_min_slots(table, cust_id, filters, min_distinct_slots_per_day=min_slots)
                ok = (cur >= need_days)

        # --------------------
        # 6) app_event
        # --------------------
        elif unlock_type == "app_event":
            event = rule.get("event")
            need = int(rule.get("count", 0))
            cur = fetch_event_count(cust_id, event)
            ok = (cur >= need)

        # --------------------
        # 7) count_join (CUS_FOOD_TS x FOOD_TB)
        # --------------------
        elif unlock_type == "count_join":
            filters = rule.get("filters", {})
            source_type = filters.get("FOOD_TB.source_type")
            need = int(rule.get("count", 0))
            if source_type:
                cur = count_join_source_type(cust_id, source_type)
                ok = (cur >= need)

        # unknown unlock_type -> skip (안전)
        else:
            ok = False

        if ok:
            ts = now_yyyymmddhhmmss()
            if insert_badge_if_not_exists(cust_id, badge_id, acquired_time=ts):
                granted.append(badge_id)
                owned.add(badge_id)

    return granted