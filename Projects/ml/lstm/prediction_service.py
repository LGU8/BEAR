# Projects/ml/lstm/prediction_service.py

from __future__ import annotations

import json
from dataclasses import dataclass

from django.db import connection
from django.utils import timezone

from ml.lstm.predictor import predict_negative_risk


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
    detail: str | None = None,  # 현재 SQL에 반영 안 되면 저장되지 않음(로그용)
) -> None:
    """
    CUS_FEEL_RISK_TH 저장 규칙:
    - risk_level: VARCHAR(1) => 'y'/'n' ONLY
    - risk_score: 점수(0~100)
    """
    now = _now_yyyymmdd_hhmmss()
    level_flag = to_risk_flag(risk_score)

    # ⚠️ 아래 SQL은 네 테이블 컬럼명에 맞춰야 함.
    # created_time/updated_time 컬럼이 실제로 없으면 제거해야 함.
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
# prediction runner
# =========================
@dataclass
class ServicePredResult:
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
    - predictor.py(predict_negative_risk)를 호출해 확률을 얻고
    - p0+p2를 risk_score(0~100)로 변환해
    - CUS_FEEL_RISK_TH에 upsert 저장한다.
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

    try:
        # 2) ✅ predictor 호출
        out = predict_negative_risk(
            cust_id=cust_id,
            source_date=source_date,
            source_slot=source_slot,
            source_seq=source_seq,
        )

        # 3) ✅ 점수화: p0+p2를 직접 사용
        if not getattr(out, "ok", False):
            p0 = 0.0
            p2 = 0.0
            p_high = 0.0
            risk_score = 0
        else:
            p0 = float(getattr(out, "p0", 0.0) or 0.0)
            p2 = float(getattr(out, "p2", 0.0) or 0.0)
            p_high = p0 + p2  # ✅ 핵심: p0+p2

            # clamp
            if p_high < 0.0:
                p_high = 0.0
            if p_high > 1.0:
                p_high = 1.0

            risk_score = int(round(p_high * 100))

        # 4) detail(로그/디버그용 JSON)
        detail_dict = {
            "ok": bool(getattr(out, "ok", False)),
            "reason": str(getattr(out, "reason", "")),
            "p0": float(p0),
            "p2": float(p2),
            "p0_plus_p2": float(p_high),
            "p_highrisk_from_predictor": float(getattr(out, "p_highrisk", 0.0) or 0.0),
            "source_date": source_date,
            "source_slot": (source_slot or "").upper(),
            "source_seq": int(source_seq or 0),
            "target_date": target_date,
            "target_slot": (target_slot or "").upper(),
            "predictor_detail": getattr(out, "detail", None),
        }
        detail_str = json.dumps(detail_dict, ensure_ascii=False)

        pred = ServicePredResult(risk_score=risk_score, detail=detail_str)

        # 5) DB upsert
        upsert_risk_row(
            cust_id=cust_id,
            target_date=target_date,
            target_slot=target_slot,
            risk_score=pred.risk_score,
            detail=pred.detail,  # ⚠️ 현재 SQL에는 저장 안 됨 (필요시 스키마/SQL 확장)
        )

        print(
            "[PREDDBG][UPSERT_OK]",
            "cust_id=",
            cust_id,
            "target=",
            f"{target_date}{target_slot}",
            "score=",
            pred.risk_score,
            "level=",
            _to_flag_level_by_score(pred.risk_score),
            "ok=",
            detail_dict["ok"],
            "reason=",
            detail_dict["reason"],
            "p0=",
            detail_dict["p0"],
            "p2=",
            detail_dict["p2"],
            "p0+p2=",
            detail_dict["p0_plus_p2"],
            "p_highrisk(pred)=",
            detail_dict["p_highrisk_from_predictor"],
            flush=True,
        )
        return True

    except Exception as e:
        print("[PREDDBG][RUN_ERR]", repr(e), flush=True)
        return False
