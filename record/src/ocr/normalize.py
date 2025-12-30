from __future__ import annotations

import re


def normalize_korean_nutrition_text(text: str) -> str:
    t = text.replace("\n", " ")
    t = t.replace(",", "")

    repl_map = {
        "Kcal": "kcal",
        "mG": "mg",
        "Mg": "mg",
        "Omg": "0mg",
        "omg": "0mg",
        "O%": "0%",
        "나트름": "나트륨",
        "트렌스지방": "트랜스지방",
        "E랜스지방": "트랜스지방",
        "콜레스테를": "콜레스테롤",
        "콜레스테를0": "콜레스테롤 0",
        "열균백": "",
    }
    for a, b in repl_map.items():
        t = t.replace(a, b)

    t = re.sub(r"\b(k\s*c\s*a\s*l)\s*[a-zA-Z]+\b", r"\1", t, flags=re.IGNORECASE)
    t = re.sub(r"\bkcai\b", "kcal", t, flags=re.IGNORECASE)
    t = re.sub(r"\bkcaI\b", "kcal", t, flags=re.IGNORECASE)

    t = re.sub(r"(\d+)\s*\.\s*(g|mg)\b", r"\1 \2", t, flags=re.IGNORECASE)
    t = re.sub(r"(총\s*내용량\s*)(\d{2,3})9\b", r"\1\2 g", t)
    t = re.sub(r"(트랜스지방)\s*([0-9]+\.[0-9]+)\b", r"\1 \2 g", t)

    t = re.sub(r"(\d)\s*(kcal)\b", r"\1 \2", t, flags=re.IGNORECASE)
    t = re.sub(r"(\d)\s*(mg)\b", r"\1 \2", t, flags=re.IGNORECASE)
    t = re.sub(r"(\d)\s*(g)\b", r"\1 \2", t, flags=re.IGNORECASE)

    t = re.sub(r"(\d)\s*%", r"\1 %", t)
    t = re.sub(r"\b(mg|g)\s*(\d+)\s*%", r"\1 \2 %", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(\d+)\s*m\s*(\d+)\s*%\b", r"\1 mg \2 %", t, flags=re.IGNORECASE)

    t = re.sub(r"\s+", " ", t).strip()
    return t
