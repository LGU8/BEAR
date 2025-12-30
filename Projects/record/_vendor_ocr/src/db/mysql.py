from __future__ import annotations

import pymysql
from typing import Optional
from src.config import AppConfig


def get_conn(cfg: AppConfig) -> pymysql.connections.Connection:
    # charset/encoding은 DB_CHARSET 기준
    conn = pymysql.connect(
        host=cfg.db_host,
        port=cfg.db_port,
        user=cfg.db_user,
        password=cfg.db_password,
        db=cfg.db_name,
        charset=cfg.db_charset,
        autocommit=False,
        cursorclass=pymysql.cursors.Cursor,
    )
    return conn
