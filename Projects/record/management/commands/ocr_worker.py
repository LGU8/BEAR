# record/management/commands/ocr_worker.py
from __future__ import annotations

import io
import json
import traceback
from typing import Optional, Tuple

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from django.conf import settings


def _now14() -> str:
    # yyyymmddHHMMSS
    from datetime import datetime
    return datetime.utcnow().strftime("%Y%m%d%H%M%S")


def _fetch_pending_job(limit: int = 1):
    """
    success_yn='N' 이고 error_code가 아직 없는(또는 null) job을 하나 집어온다.
    (원하면 조건을 더 엄격하게 바꿔도 됨)
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT cust_id, rgs_dt, seq, ocr_seq, image_s3_bucket, image_s3_key
            FROM CUS_OCR_TH
            WHERE success_yn='N' AND (error_code IS NULL OR error_code='')
            ORDER BY updated_time ASC
            LIMIT %s
            """,
            [limit],
        )
        rows = cursor.fetchall()
    return rows


def _mark_error(cust_id: str, rgs_dt: str, seq: int, ocr_seq: int, code: str):
    t = _now14()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE CUS_OCR_TH
            SET updated_time=%s,
                error_code=%s
            WHERE cust_id=%s AND rgs_dt=%s AND seq=%s AND ocr_seq=%s
            """,
            [t, code, cust_id, rgs_dt, seq, ocr_seq],
        )


def _mark_success(
    cust_id: str,
    rgs_dt: str,
    seq: int,
    ocr_seq: int,
    chosen_source: str,
    roi_score: Optional[float],
    full_score: Optional[float],
):
    t = _now14()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE CUS_OCR_TH
            SET updated_time=%s,
                success_yn='Y',
                error_code=NULL,
                chosen_source=%s,
                roi_score=%s,
                full_score=%s
            WHERE cust_id=%s AND rgs_dt=%s AND seq=%s AND ocr_seq=%s
            """,
            [t, chosen_source, roi_score, full_score, cust_id, rgs_dt, seq, ocr_seq],
        )


def _upsert_result_json(cust_id: str, rgs_dt: str, seq: int, ocr_seq: int, result_json: dict):
    """
    CUS_OCR_NUTR_TS에 최종 JSON 저장.
    테이블 PK/UK 제약에 맞춰 INSERT ... ON DUPLICATE KEY UPDATE 형태로 저장.
    """
    t = _now14()
    payload = json.dumps(result_json, ensure_ascii=False)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO CUS_OCR_NUTR_TS
              (created_time, updated_time, cust_id, rgs_dt, seq, ocr_seq, result_json)
            VALUES
              (%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
              updated_time=VALUES(updated_time),
              result_json=VALUES(result_json)
            """,
            [t, t, cust_id, rgs_dt, seq, ocr_seq, payload],
        )


def _download_from_s3(bucket: str, key: str) -> bytes:
    """
    settings에 AWS 키가 없으면(=IAM Role로 접근) boto3가 자동으로 Role 사용.
    """
    import boto3

    s3 = boto3.client("s3")
    bio = io.BytesIO()
    s3.download_fileobj(bucket, key, bio)
    return bio.getvalue()


def _run_vendor_ocr(image_bytes: bytes) -> Tuple[dict, dict]:
    """
    vendor OCR pipeline 실행.
    - result: 최종 영양정보 JSON (저장용)
    - debug: chosen_source/roi_score/full_score 등 상태 정보
    """
    # vendor 코드 경로: record/_vendor_ocr/src/main.py -> run_ocr_pipeline(image)
    # main.py가 이미 run_ocr_pipeline을 import하고 있으니 그걸 직접 호출해도 되고,
    # pipeline을 직접 import해도 됨.
    from record._vendor_ocr.src.ocr.pipeline import run_ocr_pipeline

    # pipeline이 "image"를 어떤 타입으로 받는지에 따라 조정 필요:
    # 보통 bytes -> PIL.Image로 변환하거나 numpy로 읽음.
    # 여기서는 PIL로 변환해서 넣는 방식을 택함.
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    out = run_ocr_pipeline(img)

    # out 구조가 예: {"ok": True, "result": {...}, "debug": {...}} 또는 비슷할 수 있음
    # 현재 vendor artifacts 결과를 보면 debug에 roi_score/full_score 등이 있는 형태가 흔함.
    result = out.get("result") or out.get("result_json") or {}
    debug = out.get("debug") or {}

    # 혹시 pipeline이 바로 최종 dict만 반환한다면:
    if not isinstance(out, dict) or ("result" not in out and "debug" not in out):
        # out이 그냥 최종 JSON일 수 있음
        result = out if isinstance(out, dict) else {}
        debug = {}

    return result, debug


class Command(BaseCommand):
    help = "Process pending OCR jobs from CUS_OCR_TH and write results to CUS_OCR_NUTR_TS"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process just one job then exit")
        parser.add_argument("--limit", type=int, default=5, help="Max jobs per run")
        parser.add_argument("--sleep", type=float, default=0.0, help="Sleep seconds between jobs (when not --once)")

    def handle(self, *args, **opts):
        once = bool(opts["once"])
        limit = int(opts["limit"])
        sleep_s = float(opts["sleep"])

        processed = 0

        while True:
            jobs = _fetch_pending_job(limit=limit)

            if not jobs:
                self.stdout.write("[OCR_WORKER] no pending jobs")
                # cron 기반이면 여기서 종료(다음 분에 다시 실행됨)
                return

            for (cust_id, rgs_dt, seq, ocr_seq, bucket, key) in jobs:
                self.stdout.write(
                    f"[OCR_WORKER] start job={cust_id}:{rgs_dt}:{seq}:{ocr_seq} s3={bucket}/{key}"
                )
                try:
                    image_bytes = _download_from_s3(bucket, key)
                    result_json, debug = _run_vendor_ocr(image_bytes)

                    chosen_source = (
                        debug.get("final_source")
                        or debug.get("chosen_source")
                        or "R"
                    )
                    roi_score = debug.get("roi_score")
                    full_score = debug.get("full_score")

                    if not result_json:
                        _mark_error(cust_id, rgs_dt, int(seq), int(ocr_seq), "E_EMPTY")
                        self.stdout.write("[OCR_WORKER] empty result -> E_EMPTY")
                        continue

                    with transaction.atomic():
                        _upsert_result_json(
                            cust_id, rgs_dt, int(seq), int(ocr_seq), result_json
                        )
                        _mark_success(
                            cust_id,
                            rgs_dt,
                            int(seq),
                            int(ocr_seq),
                            str(chosen_source),
                            roi_score,
                            full_score,
                        )

                    self.stdout.write("[OCR_WORKER] success -> success_yn=Y")
                    processed += 1

                except Exception:
                    _mark_error(cust_id, rgs_dt, int(seq), int(ocr_seq), "E_OCR")
                    self.stdout.write("[OCR_WORKER] exception -> E_OCR")
                    self.stdout.write(traceback.format_exc())

                if once:
                    self.stdout.write(f"[OCR_WORKER] done once. processed={processed}")
                    return

            # once가 아니더라도, cron이 다시 실행하므로 1회 배치 후 종료하는 게 안전
            return
