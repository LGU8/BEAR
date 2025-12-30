# ml/behavior_llm/behavior_service.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import re

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv

from django.db import connection, transaction
from django.utils import timezone

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.messages import SystemMessage, HumanMessage

from .prompts import SYSTEM_PROMPT_ENCOURAGE, SYSTEM_PROMPT_RECOMMEND


# =========================================================
# 1) Paths (앱 기준 절대경로)
# =========================================================
BASE_DIR = Path(__file__).resolve().parent  # .../ml/behavior_llm
ASSETS_DIR = BASE_DIR / "rag_assets"
CSV_PATH = ASSETS_DIR / "behavior_numeric.csv"
CHROMA_DIR = ASSETS_DIR / "chroma_store"

# =========================================================
# 2) Settings
# =========================================================
EMBEDDING_MODEL = "text-embedding-3-large"
LLM_MODEL = "gpt-4o-mini"

RETRIEVER_K = 3
DEFAULT_QUERY = "부정적인 감정일 때, 기분 개선에 효과적인 추천 행동은 뭐야?"

RULE_W = 0.5
CF_W = 0.5
TOP_ACTION_N = 3

TIME_FMT = "%Y%m%d%H%M%S"


def _now14() -> str:
    # record/views.py와 동일하게 localtime 사용
    return timezone.localtime().strftime(TIME_FMT)


@dataclass(frozen=True)
class RiskRow:
    cust_id: str
    target_date: str
    target_slot: str
    risk_level: str  # 'y' or 'n'
    risk_score: Optional[int] = None


def _fetch_risk_row(cust_id: str, target_date: str, target_slot: str) -> RiskRow:
    sql = """
        SELECT cust_id, target_date, target_slot, risk_level, risk_score
        FROM CUS_FEEL_RISK_TH
        WHERE cust_id = %s
          AND target_date = %s
          AND target_slot = %s
        LIMIT 1
    """
    with connection.cursor() as cur:
        cur.execute(sql, [cust_id, target_date, target_slot])
        row = cur.fetchone()

    if not row:
        raise ValueError("CUS_FEEL_RISK_TH: 해당 키의 레코드를 찾지 못했습니다.")

    risk_level = str(row[3]).lower()
    risk_score = None if row[4] is None else int(row[4])

    return RiskRow(
        cust_id=str(row[0]),
        target_date=str(row[1]),
        target_slot=str(row[2]),
        risk_level=risk_level,
        risk_score=risk_score,
    )


def _upsert_behavior_recom(
    cust_id: str,
    target_date: str,
    target_slot: str,
    content: str,
) -> None:
    now14 = _now14()

    upsert_sql = """
        INSERT INTO CUS_BEH_RECOM_TH (
            created_time, updated_time,
            cust_id, target_date, target_slot,
            period_start, period_end,
            content
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            updated_time = VALUES(updated_time),
            period_start = VALUES(period_start),
            period_end   = VALUES(period_end),
            content      = VALUES(content);
    """

    with connection.cursor() as cur:
        cur.execute(
            upsert_sql,
            [
                now14,
                now14,
                cust_id,
                target_date,
                target_slot,
                target_date,  # period_start = target_date
                target_date,  # period_end   = target_date
                content,
            ],
        )


@lru_cache(maxsize=1)
def _load_top_actions() -> List[str]:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"behavior_numeric.csv를 찾지 못했습니다: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)
    need_cols = ["rule_score", "cf_score", "activity"]
    missing = [c for c in need_cols if c not in df.columns]
    if missing:
        raise ValueError(f"behavior_numeric.csv 컬럼 누락: {missing}")

    df["final_score"] = (RULE_W * df["rule_score"]) + (CF_W * df["cf_score"])
    return (
        df.sort_values("final_score", ascending=False)
          .head(TOP_ACTION_N)["activity"]
          .astype(str)
          .tolist()
    )


@lru_cache(maxsize=1)
def _get_retriever():
    if not CHROMA_DIR.exists():
        raise FileNotFoundError(f"chroma_store를 찾지 못했습니다: {CHROMA_DIR}")

    # ✅ 팀원과 동일: api_key를 코드로 넘기지 않음(환경변수 자동 사용)
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)

    vectorstore = Chroma(
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
    )
    return vectorstore.as_retriever(k=RETRIEVER_K)


@lru_cache(maxsize=1)
def _get_llm():
    # ✅ 팀원과 동일: api_key를 코드로 넘기지 않음(환경변수 자동 사용)
    return ChatOpenAI(model=LLM_MODEL)


def _retrieve_docs_text(query: str) -> str:
    retriever = _get_retriever()
    docs = retriever.invoke(query)
    return "\n\n".join([d.page_content for d in docs])


def _parse_llm_json_message(raw: str) -> str:
    """
    LLM 출력에서 JSON을 파싱해 message 문자열만 반환
    - ```json ``` 코드블록 제거
    - 실패 시 raw 그대로 반환
    """
    if not raw:
        return ""

    text = raw.strip()

    # ```json ... ``` 제거
    text = re.sub(r"```json\s*|\s*```", "", text, flags=re.IGNORECASE).strip()

    try:
        obj = json.loads(text)
        msg = obj.get("message")
        if isinstance(msg, str):
            return msg.strip()
    except Exception:
        pass

    # fallback
    return text


def _enforce_length_policy(text: str) -> str:
    t = (text or "").strip()
    if len(t) > 80:
        t = t[:80].rstrip()
    return t


def _build_messages(risk: RiskRow) -> List[Any]:
    # 최소 feeling_data: 우리 서비스 흐름에 필요한 것만
    feeling_data: Dict[str, Any] = {
        "cust_id": risk.cust_id,
        "date": risk.target_date,
        "period_start": risk.target_date,
        "period_end": risk.target_date,
        "today_risk": {
            "risk_score": risk.risk_score,
            "risk_level": 1 if risk.risk_level == "y" else 0,
        },
    }

    if risk.risk_level == "n":
        return [
            SystemMessage(content=SYSTEM_PROMPT_ENCOURAGE),
            HumanMessage(content=json.dumps(feeling_data, ensure_ascii=False)),
        ]

    human_payload = {
        "feeling_data": feeling_data,
        "top5_action": _load_top_actions(),
        "reference_docs": _retrieve_docs_text(DEFAULT_QUERY),
    }
    return [
        SystemMessage(content=SYSTEM_PROMPT_RECOMMEND),
        HumanMessage(content=json.dumps(human_payload, ensure_ascii=False)),
    ]


def generate_and_save_behavior_recom(cust_id: str, target_date: str, target_slot: str) -> str:
    """
    ✅ 팀원 방식으로 환경 통일:
    - 함수 시작 시 load_dotenv()
    - api_key 인자 직접 주입 없이 환경변수 자동 사용
    """
    # ✅ 팀원과 동일: 호출 시점에 .env 로드
    load_dotenv()

    risk = _fetch_risk_row(cust_id, target_date, target_slot)
    if risk.risk_level not in {"y", "n"}:
        raise ValueError(f"risk_level은 'y' 또는 'n'이어야 합니다. 현재: {risk.risk_level}")

    messages = _build_messages(risk)

    llm = _get_llm()
    resp = llm.invoke(messages)

    raw = getattr(resp, "content", "")
    msg = _parse_llm_json_message(raw)
    msg = _enforce_length_policy(msg)

    with transaction.atomic():
        _upsert_behavior_recom(cust_id, target_date, target_slot, msg)

    return msg
