# settings/utils/security.py
from __future__ import annotations

import hashlib
from django.contrib.auth.hashers import check_password, make_password


# Django에서 기본적으로 흔히 쓰는 알고리즘들
# (프로젝트에서 PASSWORD_HASHERS 설정을 바꾸면 여기에 추가 가능)
_DJANGO_ALGOS = {
    "pbkdf2_sha256",
    "argon2",
    "bcrypt_sha256",
    "scrypt",
}


def sha256_hex(raw: str) -> str:
    raw = (raw or "").strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_django_hashed(s: str) -> bool:
    """
    Django password hash 포맷은 일반적으로:
      algo$salt$hash  (총 3~4 토큰)
    예:
      pbkdf2_sha256$600000$...$...
      argon2$argon2id$v=19$m=...$...$...
    """
    s = (s or "").strip()
    if not s:
        return False

    # 최소 포맷 체크: algo$ 가 있어야 함
    if "$" not in s:
        return False

    algo = s.split("$", 1)[0].strip()
    if algo not in _DJANGO_ALGOS:
        return False

    # 토큰 수 체크(너무 짧으면 Django 해시로 보기 어려움)
    # pbkdf2_sha256: 4토큰, bcrypt_sha256: 3~4토큰, argon2: 더 많을 수 있음
    parts = s.split("$")
    if len(parts) < 3:
        return False

    return True


def verify_password(raw: str, stored: str) -> bool:
    """
    - stored가 Django 해시 포맷이면: check_password
    - 아니면: 레거시 SHA256(hex) 비교

    안전장치:
    - stored가 sha256 hex(64자) 형태가 아니면 레거시 비교 실패 처리
    - check_password 예외 발생 시 False
    """
    raw = (raw or "").strip()
    stored = (stored or "").strip()
    if not raw or not stored:
        return False

    # 1) Django 해시
    if is_django_hashed(stored):
        try:
            return check_password(raw, stored)
        except Exception:
            return False

    # 2) 레거시 SHA256 (정확히 64자리 hex만 인정)
    if len(stored) != 64:
        return False

    # hex 검증 (비-hex 문자열이면 레거시로도 실패)
    try:
        int(stored, 16)
    except ValueError:
        return False

    return sha256_hex(raw) == stored


def hash_password(raw: str) -> str:
    """
    앞으로는 Django 표준 해시로 저장 통일 (pbkdf2_sha256 기본).
    """
    raw = (raw or "").strip()
    return make_password(raw)