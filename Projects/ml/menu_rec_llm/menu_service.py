# Projects/ml/menu_rec_llm/menu_service.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional, Dict, Any, List

from dotenv import load_dotenv
from django.conf import settings
from django.db import connection
from django.utils import timezone

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.messages import SystemMessage, HumanMessage

from .prompts import SYSTEM_PROMPT_MENU_RAG_RECOMMEND


# =========================================================
# 1) Paths
# =========================================================
LLM_DIR = Path(settings.BASE_DIR) / "LLM"
CHROMA_DIR = LLM_DIR / "Chain" / "menu_chroma_store"


# =========================================================
# 2) Settings
# =========================================================
EMBEDDING_MODEL = "text-embedding-3-large"
LLM_MODEL = "gpt-4o-mini"
RETRIEVER_K = 3
TIME_FMT = "%Y%m%d%H%M%S"


def _now14() -> str:
    return timezone.localtime().strftime(TIME_FMT)


# =========================================================
# 3) OpenAI Key Helpers
# =========================================================
def _get_openai_key() -> str:
    return (os.getenv("OPENAI_API_KEY") or "").strip()


def _ensure_openai_key_or_raise() -> None:
    if not _get_openai_key():
        raise RuntimeError("OPENAI_API_KEY is missing or blank")


# =========================================================
# 4) RAG / LLM Loaders
# =========================================================
@lru_cache(maxsize=1)
def _get_retriever(api_key: str):
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=api_key)
    vs = Chroma(
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
    )
    return vs.as_retriever(k=RETRIEVER_K)


@lru_cache(maxsize=1)
def _get_llm(api_key: str):
    return ChatOpenAI(model=LLM_MODEL, api_key=api_key)


def _retrieve_docs_text(query: str) -> str:
    api_key = _get_openai_key()
    _ensure_openai_key_or_raise()
    retriever = _get_retriever(api_key)
    docs = retriever.invoke(query)
    return "\n\n".join(
        (d.page_content or "").strip() for d in docs if (d.page_content or "").strip()
    )


# =========================================================
# 5) Parsing / Policy
# =========================================================
def _strip_code_fence(raw: str) -> str:
    text = (raw or "").strip()
    text = re.sub(r"```json|```", "", text).strip()
    return text


def _parse_llm_json(raw: str) -> Dict[str, Any]:
    text = _strip_code_fence(raw)
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        # JSON이 깨졌다면 message로라도 잡기
        return {"message": text}


def _sanitize_food_name(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s  # food_name 컬럼 길이 가드(이미지 기준 VARCHAR(45)였음)


def _fallback_food_name(mood: str, energy: str) -> str:
    m = (mood or "").lower()
    e = (energy or "").lower()

    if "low" in e or "tired" in e or "피곤" in e:
        return "따뜻한 미음"
    if "sad" in m or "depress" in m or "우울" in m:
        return "따뜻한 죽"
    return "가벼운 국밥"


def _fallback_message() -> str:
    return "부담 없는 한 끼로 컨디션을 천천히 올려보자."


# =========================================================
# 6) DB Upsert
# =========================================================
def _upsert_menu_recom_rag(
    *,
    cust_id: str,
    rgs_dt: str,
    rec_time_slot: str,
    food_name: str,
) -> None:
    t = _now14()
    food_name = (food_name or "").strip()[:100].rstrip()

    sql = """
        INSERT INTO MENU_RECOM_TH
        (created_time, updated_time, cust_id, rgs_dt, rec_time_slot, rec_type, food_id, food_name)
        VALUES
        (%s, %s, %s, %s, %s, 'R', 'RAG', %s)
        ON DUPLICATE KEY UPDATE
            updated_time = VALUES(updated_time),
            food_id = 'RAG',
            food_name = VALUES(food_name);
    """
    with connection.cursor() as cur:
        cur.execute(sql, [t, t, cust_id, rgs_dt, rec_time_slot, food_name])


# =========================================================
# 7) Public API
# =========================================================
def generate_and_save_menu_rag(
    *,
    cust_id: str,
    rgs_dt: str,
    rec_time_slot: str,
    mood: str,
    energy: str,
    recent_foods: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    RAG 기반 메뉴 추천(1개) 생성 후 MENU_RECOM_TH에 저장.
    - 실패해도 예외를 올리지 않고 fallback 저장까지 시도.
    반환:
      {"ok": bool, "food_name": str, "message": str}
    """

    # 로컬에서만 .env 로딩
    if os.getenv("ENV", "").lower() in {"local", "dev"}:
        load_dotenv()

    cust_id = (cust_id or "").strip()
    rgs_dt = (rgs_dt or "").strip()
    rec_time_slot = (rec_time_slot or "").strip().upper()
    mood_n = (mood or "").strip().lower()
    energy_n = (energy or "").strip().lower()

    if not (cust_id and rgs_dt and rec_time_slot):
        return {"ok": False, "food_name": "", "message": ""}

    query = f"""
    사용자 상태:
    - mood: {mood_n}
    - energy: {energy_n}
    - 추천 대상 슬롯: {rec_time_slot}
    - 최근 먹은 음식: {(", ".join((recent_foods or [])[:10]) if recent_foods else "없음")}
    요청:
    다음 끼니에 먹기 부담 없는 메뉴 1개를 추천해줘.
    """.strip()

    api_key = _get_openai_key()
    food_name = ""
    message = ""

    try:
        _ensure_openai_key_or_raise()

        reference = _retrieve_docs_text(query)
        llm = _get_llm(api_key)

        messages = [
            SystemMessage(content=SYSTEM_PROMPT_MENU_RAG_RECOMMEND),
            HumanMessage(
                content=json.dumps(
                    {
                        "mood": mood_n,
                        "energy": energy_n,
                        "rgs_dt": rgs_dt,
                        "rec_time_slot": rec_time_slot,
                        "recent_foods": (recent_foods or [])[:10],
                        "reference": reference,
                    },
                    ensure_ascii=False,
                )
            ),
        ]

        resp = llm.invoke(messages)
        raw = getattr(resp, "content", "") or ""
        obj = _parse_llm_json(raw)

        raw_food_name = _sanitize_food_name(str(obj.get("food_name", "")))
        raw_message = (str(obj.get("message", "")) or "").strip()

        # 저장용 메뉴명: message 우선
        menu_name_to_save = _sanitize_food_name(str(obj.get("message", "")).strip())
        if not menu_name_to_save:
            menu_name_to_save = _sanitize_food_name(
                _fallback_food_name(mood_n, energy_n)
            )

        # DB 컬럼이 VARCHAR(100)이므로 100자 제한(필수)
        menu_name_to_save = (menu_name_to_save or "").strip()[:100].rstrip()

        # 화면에서 쓸 멘트가 필요하면(지금은 정책상 메뉴명=message라서 동일하게 처리 가능)
        food_name = menu_name_to_save
        message = menu_name_to_save  # UI에 쓸게 있으면 유지, 아니면 생략 가능

        _upsert_menu_recom_rag(
            cust_id=cust_id,
            rgs_dt=rgs_dt,
            rec_time_slot=rec_time_slot,
            food_name=menu_name_to_save,  # ✅ message 기반 메뉴명 저장
        )
        return {"ok": True, "food_name": food_name, "message": message}

    except Exception:
        try:
            menu_name_to_save = _sanitize_food_name(
                _fallback_food_name(mood_n, energy_n)
            )
            menu_name_to_save = (menu_name_to_save or "").strip()[:100].rstrip()

            _upsert_menu_recom_rag(
                cust_id=cust_id,
                rgs_dt=rgs_dt,
                rec_time_slot=rec_time_slot,
                food_name=menu_name_to_save,
            )
            return {
                "ok": False,
                "food_name": menu_name_to_save,
                "message": _fallback_message(),
            }
        except Exception:
            return {"ok": False, "food_name": "", "message": ""}
