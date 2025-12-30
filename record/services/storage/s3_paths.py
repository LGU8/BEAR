import os
from pathlib import Path


def build_ocr_input_key(
    *, env: str, cust_id: str, rgs_dt: str, seq: int, filename: str
) -> str:
    # filename 안전 처리(경로 제거)
    safe_name = Path(filename).name
    return f"ocr-input/{env}/{cust_id}/{rgs_dt}/{seq}/{safe_name}"


def get_env_name() -> str:
    return (os.getenv("APP_ENV") or "dev").strip()
