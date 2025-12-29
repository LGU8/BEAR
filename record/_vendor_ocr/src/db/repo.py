from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from src.utils.timeutil import now_yyyymmddhhmmss
from src.db.sql import SQL_NEXT_OCR_SEQ, SQL_UPSERT_OCR_TH, SQL_UPSERT_OCR_NUTR


def get_next_ocr_seq(conn, cust_id: str, rgs_dt: str, seq: int) -> int:
    with conn.cursor() as cur:
        cur.execute(SQL_NEXT_OCR_SEQ, (cust_id, rgs_dt, seq))
        row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 1


def upsert_ocr_th(
    conn,
    cust_id: str,
    rgs_dt: str,
    seq: int,
    ocr_seq: int,
    image_s3_bucket: Optional[str],
    image_s3_key: Optional[str],
    chosen_source: str,  # "R" or "F"
    roi_score: Optional[float],
    full_score: Optional[float],
    success_yn: str,  # "Y" or "N"
    error_code: Optional[str],
) -> None:
    ts = now_yyyymmddhhmmss()
    with conn.cursor() as cur:
        cur.execute(
            SQL_UPSERT_OCR_TH,
            (
                cust_id,
                rgs_dt,
                seq,
                ocr_seq,
                image_s3_bucket,
                image_s3_key,
                chosen_source,
                roi_score,
                full_score,
                success_yn,
                error_code,
                ts,
                ts,
            ),
        )


def upsert_ocr_nutr_ts(
    conn,
    cust_id: str,
    rgs_dt: str,
    seq: int,
    ocr_seq: int,
    result_json: Dict[str, Any],
) -> None:
    ts = now_yyyymmddhhmmss()
    payload = json.dumps(result_json, ensure_ascii=False)
    with conn.cursor() as cur:
        cur.execute(
            SQL_UPSERT_OCR_NUTR, (cust_id, rgs_dt, seq, ocr_seq, payload, ts, ts)
        )


def normalize_source_to_rf(final_source: str) -> str:
    s = (final_source or "").upper()
    if s in ("ROI", "R"):
        return "R"
    if s in ("FULL", "F"):
        return "F"
    return "R"


# src/db/repo.py


def save_ocr_result_to_db(
    conn,
    cust_id: str,
    rgs_dt: str,
    seq: int,
    image_identifier: str,
    ocr_result: Dict[str, Any],
    write_failed_json: bool = False,
) -> Tuple[int, str]:
    try:
        conn.begin()
        ocr_seq = get_next_ocr_seq(conn, cust_id, rgs_dt, seq)

        debug = ocr_result.get("debug") or {}
        roi_score = debug.get("roi_score")
        full_score = debug.get("full_score")
        chosen_source = normalize_source_to_rf(ocr_result.get("final_source", ""))

        # ✅ S3 미사용 더미 bucket
        bucket = "LOCAL"  # <- NOT NULL 회피
        key = image_identifier  # local://...

        upsert_ocr_th(
            conn,
            cust_id=cust_id,
            rgs_dt=rgs_dt,
            seq=seq,
            ocr_seq=ocr_seq,
            image_s3_bucket=bucket,  # ✅ 변경
            image_s3_key=key,  # ✅ 유지
            chosen_source=chosen_source,
            roi_score=roi_score,
            full_score=full_score,
            success_yn="Y",
            error_code=None,
        )

        upsert_ocr_nutr_ts(
            conn,
            cust_id=cust_id,
            rgs_dt=rgs_dt,
            seq=seq,
            ocr_seq=ocr_seq,
            result_json=ocr_result,
        )

        conn.commit()
        return ocr_seq, "Y"

    except Exception as e:
        conn.rollback()

        try:
            conn.begin()
            ocr_seq = get_next_ocr_seq(conn, cust_id, rgs_dt, seq)

            bucket = "LOCAL"
            key = image_identifier

            upsert_ocr_th(
                conn,
                cust_id=cust_id,
                rgs_dt=rgs_dt,
                seq=seq,
                ocr_seq=ocr_seq,
                image_s3_bucket=bucket,
                image_s3_key=key,
                chosen_source="R",
                roi_score=None,
                full_score=None,
                success_yn="N",
                error_code="E_OCR",
            )

            if write_failed_json:
                fail_json = {
                    "success": False,
                    "error_code": "E_OCR",
                    "error_message": str(e)[:500],
                    "final_source": "R",
                    "debug": {},
                }
                upsert_ocr_nutr_ts(
                    conn,
                    cust_id=cust_id,
                    rgs_dt=rgs_dt,
                    seq=seq,
                    ocr_seq=ocr_seq,
                    result_json=fail_json,
                )

            conn.commit()
            return ocr_seq, "N"
        except Exception:
            conn.rollback()
            raise
