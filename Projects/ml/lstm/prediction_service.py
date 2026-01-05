# Projects/ml/lstm/prediction_service.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from django.db import connection, transaction
from django.utils import timezone


# =========================
# util
# =========================
TIME_FMT = "%Y%m%d%H%M%S"


def _now_yyyymmdd_hhmmss() -> str:
    # 운영/로컬 동일하게 timezone 기반(권장)
    return timezone.localtime().strftime(TIME_FMT)


def _to_flag_level_by_score(score: int | float | None) -> str:
    """
    DB 설계 기준:
    - risk_score >= 30 => 'y'
    - else => 'n'
    """
    try:
        v = float(score or 0)
    except Exception:
        v = 0.0
    return "y" if v >= 30 else "n"


def to_risk_flag(risk_score: int | float | None) -> str:
    try:
        return "y" if float(risk_score or 0) >= 30 else "n"
    except Exception:
        return "n"


# =========================
# DB upsert
# =========================
def upsert_risk_row(
    cust_id: str,
    target_date: str,  # 'YYYYMMDD'
    target_slot: str,  # 'M'/'L'/'D'
    risk_score: int,  # 0~100
    detail: str | None = None,
) -> None:
    """
    CUS_FEEL_RISK_TH 저장 규칙:
    - risk_level: VARCHAR(1) => 'y'/'n' ONLY
    - risk_score: 점수(0~100)
    - detail: (있으면) 별도 컬럼에 저장하거나 JSON 문자열 저장 (컬럼 존재 시)
    """
    now = _now_yyyymmdd_hhmmss()
    level_flag = to_risk_flag(risk_score)

    # ⚠️ 아래 SQL은 네 테이블 컬럼명에 맞춰야 함.
    # 너가 timeline에서 조회한 컬럼은 (risk_score, risk_level, updated_time) 형태였으니 그 기준으로 작성.
    # created_time/updated_time 컬럼이 실제로 존재하면 사용하고, 없으면 제거해야 함.
    sql = """
            INSERT INTO CUS_FEEL_RISK_TH (
                created_time, updated_time,
                cust_id, target_date, target_slot,
                risk_score, risk_level
            ) VALUES (
                %s, %s,
                %s, %s, %s,
                %s, %s
            )
            ON DUPLICATE KEY UPDATE
                updated_time = VALUES(updated_time),
                risk_score  = VALUES(risk_score),
                risk_level  = VALUES(risk_level)
        """

    with connection.cursor() as cursor:
        cursor.execute(
            sql,
            [now, now, cust_id, target_date, target_slot, int(risk_score), level_flag],
        )


# =========================
# prediction runner (예시)
# =========================
@dataclass
class PredResult:
    risk_score: int
    detail: str = ""


def run_prediction_for_date(
    cust_id: str,
    source_date: str,
    source_slot: str,
    source_seq: int,
    target_date: str,
    target_slot: str,
    skip_if_exists: bool = False,
) -> bool:
    """
    - 여기서 모델 예측 실행 후
    - upsert_risk_row로 저장
    """
    # 1) 이미 존재하면 스킵(배치용)
    if skip_if_exists:
        sql_exists = """
            SELECT 1
            FROM CUS_FEEL_RISK_TH
            WHERE cust_id=%s AND target_date=%s AND target_slot=%s
            LIMIT 1
        """
        with connection.cursor() as cursor:
            cursor.execute(sql_exists, [cust_id, target_date, target_slot])
            if cursor.fetchone() is not None:
                print(
                    "[PREDDBG][SKIP] already exists",
                    cust_id,
                    target_date,
                    target_slot,
                    flush=True,
                )
                return True

    # 2) (여기서) 실제 predictor 호출해서 risk_score 계산해야 함
    #    아래는 예시. 너 프로젝트에서는 predictor.py의 결과를 받아오겠지.
    pred = PredResult(risk_score=25, detail="")

    try:
        upsert_risk_row(
            cust_id=cust_id,
            target_date=target_date,
            target_slot=target_slot,
            risk_score=pred.risk_score,
            detail=pred.detail,
        )
        print(
            "[PREDDBG][UPSERT_OK]",
            cust_id,
            target_date,
            target_slot,
            "score=",
            pred.risk_score,
            "level=",
            _to_flag_level_by_score(pred.risk_score),
            flush=True,
        )
        return True
    except Exception as e:
        print("[PREDDBG][UPSERT_ERR]", repr(e), flush=True)
        return False
