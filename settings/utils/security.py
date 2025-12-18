# settings/utils/security.py
from __future__ import annotations

import hashlib

def sha256_hex(raw: str) -> str:
    raw = (raw or "").strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def has_letter_and_number(raw: str) -> bool:
    s = (raw or "")
    has_letter = any(c.isalpha() for c in s)
    has_number = any(c.isdigit() for c in s)
    return has_letter and has_number
