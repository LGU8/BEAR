# record/management/commands/ocr_worker.py
from __future__ import annotations

import io
import json
import traceback
from typing import Optional, Tuple
from PIL import Image, UnidentifiedImageError

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

# record/management/commands/ocr_worker.py
def _run_vendor_ocr(image_bytes: bytes):
    import os
    import sys
    import traceback
    from PIL import Image, UnidentifiedImageError

    debug = {}

    # ✅ Django BASE_DIR (/var/app/current/Projects)
    try:
        from django.conf import settings
        base_dir = str(settings.BASE_DIR)
    except Exception:
        base_dir = os.getcwd()

    # ✅ vendor root: .../Projects/record/_vendor_ocr
    vendor_root = os.path.join(base_dir, "record", "_vendor_ocr")
    debug["vendor_root"] = vendor_root

    # ✅ sys.path에 vendor_root를 올려서 `import src...`가 가능하게
    if vendor_root not in sys.path:
        sys.path.insert(0, vendor_root)
    debug["sys_path_head"] = sys.path[:5]

    # ✅ 1) bytes → PIL Image 디코드 (깨진 이미지면 여기서 잡아 E_BAD_IMAGE로 분기)
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()  # 실제 디코딩 강제
        debug["pil_format"] = img.format
        debug["pil_size"] = img.size
        debug["pil_mode"] = img.mode
    except UnidentifiedImageError:
        debug["error_code"] = "E_BAD_IMAGE"
        debug["exc"] = "UnidentifiedImageError"
        debug["traceback"] = traceback.format_exc()
        return None, debug
    except Exception:
        debug["error_code"] = "E_BAD_IMAGE"
        debug["exc"] = "PIL_DECODE_FAIL"
        debug["traceback"] = traceback.format_exc()
        return None, debug

    # ✅ 2) vendor import & 실행
    try:
        from src.ocr.pipeline import run_ocr_pipeline

        # ⚠️ 여기서 vendor가 받는 입력 타입이 무엇인지에 따라 3가지 중 하나로 맞춰야 함
        # (A) PIL Image를 받는 경우 (가장 흔함)
        result_json = run_ocr_pipeline(img)

        # (B) bytes를 받는 경우라면 위 줄 대신:
        # result_json = run_ocr_pipeline(image_bytes)

        # (C) numpy array를 받는 경우라면:
        # import numpy as np
        # result_json = run_ocr_pipeline(np.array(img))

        return result_json, debug

    except Exception as e:
        debug["error_code"] = "E_OCR"
        debug["exc"] = repr(e)
        debug["traceback"] = traceback.format_exc()
        raise



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
                return  # cron 기반이면 종료

            for (cust_id, rgs_dt, seq, ocr_seq, bucket, key) in jobs:
                job_str = f"{cust_id}:{rgs_dt}:{seq}:{ocr_seq}"
                self.stdout.write(f"[OCR_WORKER] start job={job_str} s3={bucket}/{key}")

                try:
                    image_bytes = _download_from_s3(bucket, key)

                    result_json, debug = _run_vendor_ocr(image_bytes)
                    debug = debug or {}

                    # ✅ 1) PIL/vendor 단계에서 "이미지 깨짐" 판정
                    dbg_code = debug.get("error_code")
                    if dbg_code == "E_BAD_IMAGE":
                        _mark_error(cust_id, rgs_dt, int(seq), int(ocr_seq), "E_BAD_IMAGE")
                        self.stdout.write("[OCR_WORKER] bad image -> E_BAD_IMAGE")
                        continue

                    # ✅ 2) vendor 결과 비었음
                    if not result_json:
                        _mark_error(cust_id, rgs_dt, int(seq), int(ocr_seq), "E_EMPTY")
                        self.stdout.write("[OCR_WORKER] empty result -> E_EMPTY")
                        continue

                    # ✅ 3) 성공 처리에 필요한 메타 추출(없으면 fallback)
                    chosen_source = (
                        debug.get("final_source")
                        or debug.get("chosen_source")
                        or "R"
                    )
                    roi_score = debug.get("roi_score")
                    full_score = debug.get("full_score")

                    with transaction.atomic():
                        _upsert_result_json(cust_id, rgs_dt, int(seq), int(ocr_seq), result_json)
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

                except Exception as e:
                    _mark_error(cust_id, rgs_dt, int(seq), int(ocr_seq), "E_OCR")
                    self.stdout.write(f"[OCR_WORKER] exception -> E_OCR job={job_str} err={repr(e)}")
                    self.stdout.write(traceback.format_exc())

                if once:
                    self.stdout.write(f"[OCR_WORKER] done once. processed={processed}")
                    return

            # cron이면 1회 배치 후 종료
            return
