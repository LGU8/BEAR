from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    data_dir: Path
    artifact_dir: Path

    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    db_charset: str
    db_timezone: str


def load_config(env_path: str | None = None) -> AppConfig:
    if env_path:
        load_dotenv(env_path)
    else:
        load_dotenv()

    data_dir = Path(os.getenv("DATA_DIR", "./assets/image_data")).resolve()
    artifact_dir = Path(os.getenv("ARTIFACT_DIR", "./artifacts")).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    db_host = os.getenv("DB_HOST", "").strip()
    db_port = int(os.getenv("DB_PORT", "3306"))
    db_user = os.getenv("DB_USER", "admin").strip()
    db_password = os.getenv("DB_PASSWORD", "").strip()
    db_name = os.getenv("DB_NAME", "").strip()
    db_charset = os.getenv("DB_CHARSET", "utf8mb4").strip()
    db_timezone = os.getenv("DB_TIMEZONE", "+09:00").strip()

    if not db_host or not db_password or not db_name:
        raise ValueError("DB_HOST/DB_PASSWORD/DB_NAME must be set in .env")

    return AppConfig(
        data_dir=data_dir,
        artifact_dir=artifact_dir,
        db_host=db_host,
        db_port=db_port,
        db_user=db_user,
        db_password=db_password,
        db_name=db_name,
        db_charset=db_charset,
        db_timezone=db_timezone,
    )
