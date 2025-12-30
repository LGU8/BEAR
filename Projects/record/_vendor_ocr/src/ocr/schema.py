from __future__ import annotations

from typing import Dict, Any, List, Tuple
import re


def build_schema_v1(parsed: Dict[str, Any]) -> List[Dict[str, str]]:
    def to_amount_pct(key: str) -> Tuple[str, str]:
        item = parsed.get(key, {}) or {}
        txt = (item.get("text") or "").strip()
        if not txt:
            return "", ""

        m = re.search(r"^(.*?)(?:\s+([0-9.]+%)\s*)?$", txt)
        if not m:
            return txt.replace(" ", ""), ""

        amount = (m.group(1) or "").strip().replace(" ", "")
        pct = (m.group(2) or "").strip()
        return amount, pct

    rows = []

    amt, pct = to_amount_pct("열량")
    rows.append(
        {
            "분류": "일반성분",
            "영양성분": "에너지",
            "1회 제공량 기준": amt,
            "1일 기준치(%)": pct,
        }
    )

    amt, pct = to_amount_pct("탄수화물")
    rows.append(
        {
            "분류": "일반성분",
            "영양성분": "탄수화물",
            "1회 제공량 기준": amt,
            "1일 기준치(%)": pct,
        }
    )

    amt, pct = to_amount_pct("당류")
    rows.append(
        {
            "분류": "일반성분",
            "영양성분": "당류",
            "1회 제공량 기준": amt,
            "1일 기준치(%)": pct,
        }
    )

    amt, pct = to_amount_pct("지방")
    rows.append(
        {
            "분류": "일반성분",
            "영양성분": "지방",
            "1회 제공량 기준": amt,
            "1일 기준치(%)": pct,
        }
    )

    amt, pct = to_amount_pct("단백질")
    rows.append(
        {
            "분류": "일반성분",
            "영양성분": "단백질",
            "1회 제공량 기준": amt,
            "1일 기준치(%)": pct,
        }
    )

    amt, pct = to_amount_pct("나트륨")
    rows.append(
        {
            "분류": "무기질",
            "영양성분": "나트륨",
            "1회 제공량 기준": amt,
            "1일 기준치(%)": pct,
        }
    )

    amt, pct = to_amount_pct("트랜스지방")
    rows.append(
        {
            "분류": "지방산",
            "영양성분": "트랜스지방산",
            "1회 제공량 기준": amt,
            "1일 기준치(%)": pct,
        }
    )

    amt, pct = to_amount_pct("포화지방")
    rows.append(
        {
            "분류": "지방산",
            "영양성분": "포화지방산",
            "1회 제공량 기준": amt,
            "1일 기준치(%)": pct,
        }
    )

    amt, pct = to_amount_pct("콜레스테롤")
    rows.append(
        {
            "분류": "지방산",
            "영양성분": "콜레스테롤",
            "1회 제공량 기준": amt,
            "1일 기준치(%)": pct,
        }
    )

    return rows
