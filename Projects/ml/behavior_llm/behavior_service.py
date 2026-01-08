# ml/behavior_llm/behavior_service.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv

from django.conf import settings  # ✅ 추가
from django.db import connection, transaction
from django.utils import timezone

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.messages import SystemMessage, HumanMessage

from .prompts import SYSTEM_PROMPT_ENCOURAGE, SYSTEM_PROMPT_RECOMMEND


# =========================================================
# 1) Paths
# =========================================================

# (A) 기존 유지: 이 파일 기준 위치 (CSV 등 rag_assets 용)
BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "rag_assets"
LLM_DIR = Path(settings.BASE_DIR) / "LLM"
CSV_PATH = LLM_DIR / "RAG" / "behavior_numeric.csv"
CHROMA_DIR = LLM_DIR / "Chain" / "chroma_store"


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
    return timezone.localtime().strftime(TIME_FMT)


# =========================================================
# 3) OpenAI Key Helpers (핵심)
# =========================================================
def _get_openai_key() -> str:
    """
    OPENAI_API_KEY를 안전하게 읽는다.
    - strip()으로 공백/개행 제거
    """
    return (os.getenv("OPENAI_API_KEY") or "").strip()


def _ensure_openai_key_or_raise() -> None:
    if not _get_openai_key():
        raise RuntimeError("OPENAI_API_KEY is missing or blank")


# =========================================================
# 4) Data Structures
# =========================================================
@dataclass(frozen=True)
class RiskRow:
    cust_id: str
    target_date: str
    target_slot: str
    risk_level: str  # 'y' or 'n'
    risk_score: Optional[int] = None


# =========================================================
# 5) DB Helpers
# =========================================================
def _fetch_risk_row(cust_id: str, target_date: str, target_slot: str) -> RiskRow:
    sql = """
        SELECT cust_id, target_date, target_slot, risk_level, risk_score
        FROM CUS_FEEL_RISK_TH
        WHERE cust_id=%s AND target_date=%s AND target_slot=%s
        LIMIT 1
    """
    with connection.cursor() as cur:
        cur.execute(sql, [cust_id, target_date, target_slot])
        row = cur.fetchone()

    if not row:
        raise ValueError("CUS_FEEL_RISK_TH row not found")

    return RiskRow(
        cust_id=str(row[0]),
        target_date=str(row[1]),
        target_slot=str(row[2]),
        risk_level=str(row[3]).lower(),
        risk_score=None if row[4] is None else int(row[4]),
    )


def _upsert_behavior_recom(
    cust_id: str,
    target_date: str,
    target_slot: str,
    content: str,
) -> None:
    now14 = _now14()

    sql = """
        INSERT INTO CUS_BEH_RECOM_TH (
            created_time, updated_time,
            cust_id, target_date, target_slot,
            period_start, period_end,
            content
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            updated_time=VALUES(updated_time),
            content=VALUES(content);
    """
    with connection.cursor() as cur:
        cur.execute(
            sql,
            [
                now14,
                now14,
                cust_id,
                target_date,
                target_slot,
                target_date,
                target_date,
                content,
            ],
        )


# =========================================================
# 6) RAG / LLM Loaders
# =========================================================
@lru_cache(maxsize=1)
def _load_top_actions() -> List[str]:
    df = pd.read_csv(CSV_PATH)
    df["final_score"] = RULE_W * df["rule_score"] + CF_W * df["cf_score"]
    return (
        df.sort_values("final_score", ascending=False)
        .head(TOP_ACTION_N)["activity"]
        .astype(str)
        .tolist()
    )


@lru_cache(maxsize=1)
def _get_retriever(api_key: str):
    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        api_key=api_key,
    )
    vs = Chroma(
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
    )
    return vs.as_retriever(k=RETRIEVER_K)


@lru_cache(maxsize=1)
def _get_llm(api_key: str):
    return ChatOpenAI(
        model=LLM_MODEL,
        api_key=api_key,
    )


# =========================================================
# 7) Message Builders
# =========================================================
def _retrieve_docs_text(query: str) -> str:
    api_key = _get_openai_key()
    _ensure_openai_key_or_raise()
    retriever = _get_retriever(api_key)
    docs = retriever.invoke(query)
    return "\n\n".join(d.page_content for d in docs)


def _parse_llm_json_message(raw: str) -> str:
    if not raw:
        return ""
    text = re.sub(r"```json|```", "", raw).strip()
    try:
        obj = json.loads(text)
        return obj.get("message", text).strip()
    except Exception:
        return text


def _enforce_length_policy(text: str) -> str:
    return (text or "")[:80].rstrip()


def _build_messages(risk: RiskRow) -> List[Any]:
    if risk.risk_level == "n":
        return [
            SystemMessage(content=SYSTEM_PROMPT_ENCOURAGE),
            HumanMessage(
                content=json.dumps({"risk_score": risk.risk_score}, ensure_ascii=False)
            ),
        ]

    return [
        SystemMessage(content=SYSTEM_PROMPT_RECOMMEND),
        HumanMessage(
            content=json.dumps(
                {
                    "risk_score": risk.risk_score,
                    "top_actions": _load_top_actions(),
                    "reference": _retrieve_docs_text(DEFAULT_QUERY),
                },
                ensure_ascii=False,
            )
        ),
    ]


def _fallback_message(risk: RiskRow) -> str:
    if risk.risk_level == "y":
        return "지금은 컨디션 회복이 우선이에요. 물 한 잔과 짧은 휴식을 권해요."
    return "오늘 흐름이 나쁘지 않아요. 수분 보충과 가벼운 휴식을 유지해요."


# =========================================================
# 8) Public API
# =========================================================
def generate_and_save_behavior_recom(
    cust_id: str,
    target_date: str,
    target_slot: str,
    reason: Optional[str] = None,
) -> str:
    """
    행동 추천 생성 + DB 저장
    """

    # ✅ 로컬에서만 .env 로딩
    if os.getenv("ENV", "").lower() in {"local", "dev"}:
        load_dotenv()

    api_key = _get_openai_key()
    print("[BEHDBG][KEY]", "present=", bool(api_key), "len=", len(api_key), flush=True)

    risk = _fetch_risk_row(cust_id, target_date, target_slot)

    try:
        _ensure_openai_key_or_raise()
        messages = _build_messages(risk)
        llm = _get_llm(api_key)
        resp = llm.invoke(messages)

        raw = getattr(resp, "content", "")
        msg = _parse_llm_json_message(raw)
        msg = _enforce_length_policy(msg) or _fallback_message(risk)

        print("[BEHDBG][LLM_OK]", "len=", len(msg), flush=True)

    except Exception as e:
        print("[BEHDBG][LLM_FAIL]", repr(e), flush=True)
        msg = _fallback_message(risk)

    with transaction.atomic():
        _upsert_behavior_recom(cust_id, target_date, target_slot, msg)

    return msg
