import hashlib

def sha256_hex(raw: str) -> str:
    raw = (raw or "").strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()