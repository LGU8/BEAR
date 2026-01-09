# record/management/commands/ocr_worker.py
from __future__ import annotations

import io
import json
import traceback
from typing import Optional
from PIL import Image, UnidentifiedImageError

from django.core.management.base import BaseCommand
from django.db import connection, transaction


# =========================
# JSON 직렬화 보조
# =========================
def _to_jsonable(obj):
    """
    어떤 객체든 json.dumps 가능한 형태로 "최후" 변환한다.
    - dict/list/tuple/set 재귀 처리
    - numpy / PIL / datetime / Decimal / Path / bytes 등 광범위 대응
    - 최종적으로도 처리 불가하면 str(obj)로 강제 변환
    """
    import base64
    import datetime
    import decimal
    from pathlib import Path

    try:
        import numpy as np
    except Exception:
        np = None

    # 기본 타입
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # dict
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            # key도 안전하게 문자열화
            try:
                kk = k if isinstance(k, str) else str(k)
            except Exception:
                kk = "<non_str_key>"
            out[kk] = _to_jsonable(v)
        return out

    # list/tuple/set
    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(x) for x in obj]

    # bytes/bytearray
    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8")
        except Exception:
            return {"_b64": base64.b64encode(bytes(obj)).decode("ascii")}

    # datetime/date/time
    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)

    # Decimal
    if isinstance(obj, decimal.Decimal):
        # 소수 보존을 위해 문자열 권장
        return str(obj)

    # Path
    if isinstance(obj, Path):
        return str(obj)

    # numpy
    if np is not None:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.generic):
            try:
                return obj.item()
            except Exception:
                return str(obj)

    # PIL Image / Font 등 (Pillow 객체는 string으로만 남겨도 충분)
    try:
        from PIL import Image as PILImage
        from PIL import ImageFont as PILImageFont

        if isinstance(obj, PILImage.Image):
            return {"_pil_image": str(obj)}

        # FreeTypeFont / ImageFont 객체
        if isinstance(obj, PILImageFont.ImageFont):
            return {"_pil_font": str(obj)}
    except Exception:
        pass

    # 예: numpy scalar, cv2 keypoint, custom class 등
    # 여기까지 왔으면 JSON 불가 객체일 확률이 높으므로 최종 string 처리
    try:
        return str(obj)
    except Exception:
        return "<unstringifiable_object>"


def _json_sanitize(obj):
    """
    json.dumps가 가능한 형태로 obj를 재귀 변환한다.
    - numpy.ndarray -> list
    - numpy scalar(np.float32 등) -> python scalar
    - bytes -> utf-8 string(실패 시 base64)
    - set/tuple -> list
    - PIL.Image / PIL.Font 등 -> dict 형태로 문자열만 남김
    (※ 그래도 남는 예외 케이스는 _to_jsonable()이 마지막으로 잡는다.)
    """
    import base64

    try:
        import numpy as np
    except Exception:
        np = None

    # dict
    if isinstance(obj, dict):
        return {str(k): _json_sanitize(v) for k, v in obj.items()}

    # list/tuple/set
    if isinstance(obj, (list, tuple, set)):
        return [_json_sanitize(x) for x in obj]

    # numpy
    if np is not None:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.generic):
            try:
                return obj.item()
            except Exception:
                return str(obj)

    # bytes
    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8")
        except Exception:
            return {"_b64": base64.b64encode(bytes(obj)).decode("ascii")}

    # PIL
    try:
        from PIL import Image as PILImage
        from PIL import ImageFont as PILImageFont

        if isinstance(obj, PILImage.Image):
            return {"_pil_image": str(obj)}

        if isinstance(obj, PILImageFont.ImageFont):
            return {"_pil_font": str(obj)}
    except Exception:
        pass

    # 기본 타입(str,int,float,bool,None)은 그대로
    return obj


def _now14() -> str:
    # yyyymmddHHMMSS
    from datetime import datetime

    return datetime.utcnow().strftime("%Y%m%d%H%M%S")


# =========================
# DB helpers
# =========================
def _fetch_pending_job(limit: int = 1):
    """
    success_yn='N' 이고 error_code가 아직 없는(또는 null) job을 집어온다.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT cust_id, rgs_dt, seq, ocr_seq, image_s3_bucket, image_s3_key
            FROM CUS_OCR_TH
            WHERE success_yn='N' AND (error_code IS NULL OR error_code='')
            AND cust_id='0000000030'
            AND rgs_dt='20260108'
            AND seq=19
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


def _upsert_result_json(
    cust_id: str, rgs_dt: str, seq: int, ocr_seq: int, result_json: dict
):
    """
    CUS_OCR_NUTR_TS에 최종 JSON 저장.
    INSERT ... ON DUPLICATE KEY UPDATE
    """
    t = _now14()

    # 1) 1차: 우리가 의도한 형태로 정리
    safe = _json_sanitize(result_json)
    # 2) 2차: 남아있는 JSON 불가 객체(예: Font 등)까지 최종 제거
    safe = _to_jsonable(safe)

    payload = json.dumps(safe, ensure_ascii=False)

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


# =========================
# S3 download
# =========================
def _download_from_s3(bucket: str, key: str) -> bytes:
    """
    settings에 AWS 키가 없으면(=IAM Role로 접근) boto3가 자동으로 Role 사용.
    """
    import boto3

    s3 = boto3.client("s3")
    bio = io.BytesIO()
    s3.download_fileobj(bucket, key, bio)
    return bio.getvalue()


# =========================
# Vendor OCR runner
# =========================
def _run_vendor_ocr(image_bytes: bytes):
    import os
    import sys
    import numpy as np
    import traceback

    # ✅ Django BASE_DIR (/var/app/current/Projects)
    try:
        from django.conf import settings

        base_dir = settings.BASE_DIR
    except Exception:
        base_dir = os.getcwd()

    # ✅ vendor root: .../Projects/record/_vendor_ocr
    vendor_root = os.path.join(base_dir, "record", "_vendor_ocr")

    # vendor_root 아래에 "src" 폴더가 있고 vendor 코드가 "import src..."를 기대함
    if vendor_root not in sys.path:
        sys.path.insert(0, vendor_root)

    debug = {
        "vendor_root": vendor_root,
        "sys_path_head": sys.path[:5],
    }

    try:
        from src.ocr.pipeline import run_ocr_pipeline

        # bytes -> PIL
        try:
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except UnidentifiedImageError:
            debug["error_code"] = "E_BAD_IMAGE"
            return None, debug

        # PIL -> numpy.ndarray (H,W,3)
        np_img = np.array(pil_img)

        # vendor 호출
        result_json = run_ocr_pipeline(np_img)
        return result_json, debug

    except Exception as e:
        debug["exc"] = repr(e)
        debug["traceback"] = traceback.format_exc()
        raise


# =========================
# Command
# =========================
class Command(BaseCommand):
    help = (
        "Process pending OCR jobs from CUS_OCR_TH and write results to CUS_OCR_NUTR_TS"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--once", action="store_true", help="Process just one job then exit"
        )
        parser.add_argument("--limit", type=int, default=5, help="Max jobs per run")
        parser.add_argument(
            "--sleep", type=float, default=0.0, help="Sleep seconds between jobs"
        )

    def handle(self, *args, **opts):
        once = bool(opts["once"])
        limit = int(opts["limit"])
        sleep_s = float(opts["sleep"])  # 지금은 cron 기반이라 사용 안 해도 됨

        processed = 0

        while True:
            jobs = _fetch_pending_job(limit=limit)

            if not jobs:
                self.stdout.write("[OCR_WORKER] no pending jobs")
                return  # cron 기반이면 종료

            for cust_id, rgs_dt, seq, ocr_seq, bucket, key in jobs:
                job_str = f"{cust_id}:{rgs_dt}:{seq}:{ocr_seq}"
                self.stdout.write(f"[OCR_WORKER] start job={job_str} s3={bucket}/{key}")

                try:
                    image_bytes = _download_from_s3(bucket, key)

                    result_json, debug = _run_vendor_ocr(image_bytes)
                    debug = debug or {}

                    # 1) 이미지 깨짐
                    if debug.get("error_code") == "E_BAD_IMAGE":
                        _mark_error(
                            cust_id, rgs_dt, int(seq), int(ocr_seq), "E_BAD_IMAGE"
                        )
                        self.stdout.write("[OCR_WORKER] bad image -> E_BAD_IMAGE")
                        continue

                    # 2) 결과 비었음
                    if not result_json:
                        _mark_error(cust_id, rgs_dt, int(seq), int(ocr_seq), "E_EMPTY")
                        self.stdout.write("[OCR_WORKER] empty result -> E_EMPTY")
                        continue

                    # 3) 메타
                    chosen_source = (
                        debug.get("final_source") or debug.get("chosen_source") or "R"
                    )
                    roi_score = debug.get("roi_score")
                    full_score = debug.get("full_score")

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

                except Exception as e:
                    _mark_error(cust_id, rgs_dt, int(seq), int(ocr_seq), "E_OCR")
                    self.stdout.write(
                        f"[OCR_WORKER] exception -> E_OCR job={job_str} err={repr(e)}"
                    )
                    self.stdout.write(traceback.format_exc())

                if once:
                    self.stdout.write(f"[OCR_WORKER] done once. processed={processed}")
                    return

            # cron이면 1회 배치 후 종료
            return
