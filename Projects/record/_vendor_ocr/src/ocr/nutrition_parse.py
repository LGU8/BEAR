from __future__ import annotations

from typing import Any, Dict, List, Optional
import re

NUTRIENT_CANON = {
    "열량": ["열량", "에너지", "calories", "calonie", "calonies", "kcal"],
    "나트륨": ["나트륨"],
    "탄수화물": ["탄수화물", "총탄수화물", "carbohydrate", "carbohydrates"],
    "당류": ["당류", "총당류", "sugars", "sugar"],
    "지방": ["지방", "총지방", "fat", "totalfat"],
    "단백질": ["단백질", "protein"],
    "트랜스지방": ["트랜스지방", "transfat", "trans fat"],
    "포화지방": ["포화지방", "saturatedfat", "saturated fat"],
    "콜레스테롤": ["콜레스테롤", "cholesterol"],
}

EXPECTED_UNIT = {
    "열량": "kcal",
    "나트륨": "mg",
    "탄수화물": "g",
    "당류": "g",
    "지방": "g",
    "단백질": "g",
    "트랜스지방": "g",
    "포화지방": "g",
    "콜레스테롤": "mg",
}

KCAL_NOISE_MIN = 800


def _find_best_kcal(text: str) -> Optional[int]:
    cands = re.findall(r"(\d{1,4})\s*kcal\b", text, flags=re.IGNORECASE)
    if not cands:
        return None

    nums: List[int] = []
    for c in cands:
        try:
            nums.append(int(c))
        except Exception:
            continue
    if not nums:
        return None

    filtered = [n for n in nums if n != 2000]
    plausible = [n for n in filtered if 0 <= n <= KCAL_NOISE_MIN]
    if plausible:
        return max(plausible)
    return min(filtered) if filtered else min(nums)


def _alias_pattern(alias: str) -> str:
    a = re.escape(alias)
    return rf"(?<![가-힣]){a}(?![가-힣])"


def _extract_nutrient_value(text: str, name: str) -> Dict[str, Any]:
    out = {"found": False, "value": None, "unit": None, "pct": None, "text": ""}

    unit_expect = EXPECTED_UNIT.get(name)
    aliases = NUTRIENT_CANON.get(name, [name])

    for alias in aliases:
        a = _alias_pattern(alias)
        pat = (
            rf"{a}\s*([0-9]+(?:\.[0-9]+)?)\s*(kcal|mg|g)?\s*"
            rf"([0-9]+(?:\.[0-9]+)?)?\s*%?"
        )
        m = re.search(pat, text, flags=re.IGNORECASE)
        if not m:
            continue

        val_s = m.group(1)
        unit_s = (m.group(2) or unit_expect or "").lower()
        pct_s = m.group(3)

        try:
            val_f = float(val_s)
        except Exception:
            continue

        if not unit_s and unit_expect:
            unit_s = unit_expect

        pct_f = None
        if pct_s:
            try:
                pct_f = float(pct_s)
            except Exception:
                pct_f = None

        if pct_f is not None and pct_f >= 300:
            pct_f = None

        val_txt = f"{val_f:g}{unit_s}" if unit_s else f"{val_f:g}"
        pct_txt = f" {pct_f:g}%" if pct_f is not None else ""
        compact = (val_txt + pct_txt).strip()

        out.update(
            {
                "found": True,
                "value": val_f,
                "unit": unit_s,
                "pct": pct_f,
                "text": compact,
            }
        )
        return out

    return out


def parse_nutrition_kor_v1(normalized_text: str) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {}

    kcal = _find_best_kcal(normalized_text)
    if kcal is not None:
        parsed["열량"] = {
            "found": True,
            "value": float(kcal),
            "unit": "kcal",
            "pct": None,
            "text": f"{kcal}kcal",
        }
    else:
        parsed["열량"] = {
            "found": False,
            "value": None,
            "unit": "kcal",
            "pct": None,
            "text": "",
        }

    for k in [
        "나트륨",
        "탄수화물",
        "당류",
        "지방",
        "단백질",
        "트랜스지방",
        "포화지방",
        "콜레스테롤",
    ]:
        parsed[k] = _extract_nutrient_value(normalized_text, k)

    return parsed
