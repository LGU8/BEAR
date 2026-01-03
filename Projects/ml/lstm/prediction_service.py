# ml/lstm/prediction_service.py
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.db import connection, transaction

from ml.lstm.predictor import predict_negative_risk  # 너가 준 predictor 그대로 사용

# 행동추천: 너희 프로젝트에 이미 있는 저장 함수로 연결
# (이 함수는 "이미 있으면 UPDATE"까지 수행하도록 구현되어 있어야 함)
try:
    from ml.behavior_llm.behavior_service import generate_and_save_behavior_recom
except Exception:
    generate_and_save_behavior_recom = None


# -------------------------
# 공통 유틸
# -------------------------
def _now_yyyymmddhhmmss() -> str:
    # report와 동일하게 naive datetime 기준
    return datetime.now().strftime("%Y%m%d%H%M%S")


def _today_yyyymmdd() -> str:
    # report와 동일하게 date.today 기준
    return date.today().strftime("%Y%m%d")


def _tomorrow_yyyymmdd(today_yyyymmdd: str) -> str:
    d = datetime.strptime(today_yyyymmdd, "%Y%m%d").date()
    return (d + timedelta(days=1)).strftime("%Y%m%d")


def _norm_slot(slot: str) -> str:
    # target_slot은 오직 'M'만 존재하도록 강제
    return (slot or "").strip().upper()


def _risk_level_from_p(p_highrisk: float) -> str:
    # 너가 확정한 규칙 그대로
    if p_highrisk >= 0.30:
        return "H"
    if p_highrisk >= 0.20:
        return "M"
    return "L"


def _risk_score_from_p(p_highrisk: float) -> int:
    # 0~1 -> 0~100 정수
    # (원하면 round 대신 floor/ceil로 정책 변경 가능)
    return int(round(float(p_highrisk) * 100))


def _exists_risk_row(cust_id: str, target_date: str, target_slot: str) -> bool:
    sql = """
        SELECT 1
        FROM CUS_FEEL_RISK_TH
        WHERE cust_id = %s AND target_date = %s AND target_slot = %s
        LIMIT 1
    """
    with connection.cursor() as cur:
        cur.execute(sql, [cust_id, target_date, target_slot])
        return cur.fetchone() is not None


def _upsert_risk_row(
    *,
    cust_id: str,
    target_date: str,
    target_slot: str,
    eligible: bool,
    risk_score: Optional[int],
    risk_level: Optional[str],
    detail_json: Dict[str, Any],
) -> None:
    """
    PK(cust_id, target_date, target_slot) 기반 UPSERT.
    - 없으면 INSERT
    - 있으면 UPDATE + updated_time 갱신 + 값 갱신
    """
    now14 = _now_yyyymmddhhmmss()
    target_slot = _norm_slot(target_slot)

    # JSON은 python dict -> MySQL JSON
    detail_payload = json.dumps(detail_json, ensure_ascii=False)

    sql = """
        INSERT INTO CUS_FEEL_RISK_TH (
            created_time, updated_time,
            cust_id, target_date, target_slot,
            risk_score, risk_level,
            detail_json
        )
        VALUES (
            %s, %s,
            %s, %s, %s,
            %s, %s,
            CAST(%s AS JSON)
        )
        ON DUPLICATE KEY UPDATE
            updated_time = VALUES(updated_time),
            risk_score = VALUES(risk_score),
            risk_level = VALUES(risk_level),
            detail_json = VALUES(detail_json)
    """
    params = [
        now14,
        now14,
        cust_id,
        target_date,
        target_slot,
        risk_score,
        risk_level,
        detail_payload,
    ]

    with connection.cursor() as cur:
        cur.execute(sql, params)


# -------------------------
# 핵심 서비스: "내일 아침(M)" 예측 생성/갱신
# -------------------------
def upsert_next_morning_negative_prediction(
    *,
    cust_id: str,
    asof_yyyymmdd: Optional[str] = None,
    source: str = "event",  # "batch_20" | "dinner_event" | "late_update" 등
    skip_if_exists: bool = False,  # 배치(20:00)는 True, 이벤트는 False 권장
) -> Dict[str, Any]:
    """
    정책 반영:
    - target_slot='M' 고정
    - target_date = asof + 1
    - eligible 정의: 확률 계산 성공 여부
    - Gate 실패도 row 저장(detail_json)
    - batch에서는 row가 이미 있으면 스킵(운영 안전)
    - 이벤트(저녁 저장/수정/늦은 기록)는 무조건 재예측(UPDATE) 권장

    반환: 저장/스킵 여부 포함한 결과 dict
    """
    if asof_yyyymmdd is None:
        asof_yyyymmdd = _today_yyyymmdd()

    target_date = _tomorrow_yyyymmdd(asof_yyyymmdd)
    target_slot = "M"

    if skip_if_exists and _exists_risk_row(cust_id, target_date, target_slot):
        return {
            "skipped": True,
            "cust_id": cust_id,
            "asof": asof_yyyymmdd,
            "target_date": target_date,
            "target_slot": target_slot,
            "reason": "already_exists",
            "source": source,
        }

    # predictor 실행(너가 준 코드 그대로)
    pred = predict_negative_risk(cust_id=cust_id, D_yyyymmdd=asof_yyyymmdd)

    # eligible 재정의(확정)
    eligible = bool(pred.get("eligible") is True)

    # detail_json 구성(성공/실패 공통 메타 + pred detail 포함)
    detail_json: Dict[str, Any] = {
        "source": source,
        "asof": asof_yyyymmdd,
        "target_date": target_date,
        "target_slot": target_slot,
        # predictor가 내려주는 진단 정보
        "eligible": eligible,
    }

    # predictor 출력에서 공통적으로 유용한 필드 복사
    # (FAIL에서도 type/reason/days/missing_days 등이 있을 수 있음)
    if not eligible:
        # FAIL: 확률값 산출 불가
        detail_json["reason"] = pred.get("reason")
        detail_json["detail"] = pred.get("detail", {})
        # FAIL은 H/M/L이 없으므로 NULL 저장(테이블이 NULL 허용)
        risk_score = None
        risk_level = None
    else:
        # SUCCESS
        p_high = float(pred.get("p_highrisk", 0.0))
        risk_score = _risk_score_from_p(p_high)
        risk_level = _risk_level_from_p(p_high)

        detail_json.update(
            {
                "threshold": pred.get("threshold"),
                "p_highrisk": p_high,
                "days": pred.get("days", []),
                "missing_days": pred.get("missing_days", []),
                # 원하면 probs/p0/p2까지 저장 (디버깅에 유리)
                "probs": pred.get("probs", None),
                "p0": pred.get("p0", None),
                "p2": pred.get("p2", None),
            }
        )

    # DB 저장(UPSERT) + 행동추천 재생성(정책)
    with transaction.atomic():
        _upsert_risk_row(
            cust_id=cust_id,
            target_date=target_date,
            target_slot=target_slot,
            eligible=eligible,
            risk_score=risk_score,
            risk_level=risk_level,
            detail_json=detail_json,
        )

        # 행동추천도 동일 키로 업데이트(정책)
        if generate_and_save_behavior_recom is not None:
            # 너희 함수 시그니처가 다를 수 있으니,
            # 실제 시그니처에 맞게 아래 인자만 조정하면 됨.
            generate_and_save_behavior_recom(
                cust_id=cust_id,
                target_date=target_date,
                target_slot=target_slot,
            )

    return {
        "skipped": False,
        "cust_id": cust_id,
        "asof": asof_yyyymmdd,
        "target_date": target_date,
        "target_slot": target_slot,
        "eligible": eligible,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "source": source,
    }
