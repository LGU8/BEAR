# settings/utils/security.py
from __future__ import annotations

import hashlib
from django.contrib.auth.hashers import check_password, make_password


def sha256_hex(raw: str) -> str:
    raw = (raw or "").strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_django_hashed(s: str) -> bool:
    """
    Django password hash 포맷은 보통 algo$salt$hash 형태로 '$'를 포함.
    예: pbkdf2_sha256$600000$...$...
    """
    s = (s or "").strip()
    return ("$" in s) and (s.split("$", 1)[0] in {"pbkdf2_sha256", "argon2", "bcrypt_sha256", "scrypt"})


def verify_password(raw: str, stored: str) -> bool:
    """
    - stored가 Django 해시 포맷이면: check_password
    - 아니면: SHA256 hex 비교(레거시)
    """
    raw = (raw or "").strip()
    stored = (stored or "").strip()
    if not raw or not stored:
        return False

    if is_django_hashed(stored):
        return check_password(raw, stored)

    return sha256_hex(raw) == stored


def hash_password(raw: str) -> str:
    """
    앞으로는 Django 표준 해시로 저장 통일 (pbkdf2_sha256 기본).
    """
    raw = (raw or "").strip()
    return make_password(raw)
