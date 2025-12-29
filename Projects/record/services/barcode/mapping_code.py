# record/services/barcode/mapping_code.py
from __future__ import annotations

import os
import time
import json
import hashlib
import logging
from typing import Any, Optional

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()  # ✅ 로드만. import 시점 강제/raise 금지


# ─────────────────────────────────────────────
# 1) 에러 타입
# ─────────────────────────────────────────────
class EnvNotSetError(RuntimeError):
    """필수 환경변수 미설정"""

    pass


class UpstreamAPIError(RuntimeError):
    """외부 API 호출 실패(네트워크/인증/서버에러/JSON 파싱 등)"""

    def __init__(
        self, message: str, *, status_code: int | None = None, detail: str | None = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


# ─────────────────────────────────────────────
# 2) 공통 유틸
# ─────────────────────────────────────────────
def _require_env(name: str) -> str:
    """
    ✅ 웹 서버 안전:
    - import 시점이 아니라, "함수 호출 시점"에만 키 체크
    """
    v = os.getenv(name)
    if not v:
        raise EnvNotSetError(f"{name}가 .env에 설정되지 않았습니다.")
    return v


def _http_get_json(url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    """
    GET → JSON
    실패는 UpstreamAPIError로 통일해서 올림(뷰에서 502로 분리 가능)
    """
    t0 = time.time()
    try:
        resp = requests.get(url, timeout=timeout)
        status = resp.status_code

        if status >= 400:
            raise UpstreamAPIError(
                "외부 API가 오류를 반환했습니다.",
                status_code=status,
                detail=(resp.text or "")[:500],
            )

        try:
            return resp.json()
        except Exception as e:
            raise UpstreamAPIError(
                "외부 API 응답 JSON 파싱에 실패했습니다.",
                status_code=status,
                detail=str(e),
            )
    except requests.Timeout:
        raise UpstreamAPIError("외부 API 요청이 시간 초과되었습니다.", detail="timeout")
    except requests.RequestException as e:
        raise UpstreamAPIError(
            "외부 API 요청 중 네트워크 오류가 발생했습니다.", detail=str(e)
        )
    finally:
        logger.info("[mapping_code] GET %s (%.2fs)", url, time.time() - t0)


def make_candidate_id(
    *, barcode: str, report_no: str, product_name: str, manufacturer: str
) -> str:
    """
    후보 고정 식별자
    - 프론트에서 candidate_id로 선택 → commit에서 동일 후보를 안전하게 식별
    """
    s = f"{barcode}|{report_no}|{product_name}|{manufacturer}"
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def _as_str(x: Any) -> str:
    return str(x).strip() if x is not None else ""


# ─────────────────────────────────────────────
# 3) C005: 바코드 → 제품 후보 조회 (기본정보)
# ─────────────────────────────────────────────
def get_product_info_by_barcode(barcode: str) -> list[dict[str, Any]]:
    """
    식품안전나라 C005:
      http://openapi.foodsafetykorea.go.kr/api/{KEY}/C005/json/1/10/BAR_CD={barcode}

    반환(항상 list):
      [
        {
          "candidate_id": "...",
          "barcode": "...",
          "product_name": "...",
          "manufacturer": "...",
          "report_no": "...",
          "raw": {...}            # 원본 row
        },
        ...
      ]
    """
    api_key = _require_env("FOOD_API_KEY")

    barcode = _as_str(barcode)
    if not barcode:
        return []

    # ✅ api_key를 받아놓고 전역 FOOD_API_KEY 쓰는 버그 방지
    url = f"http://openapi.foodsafetykorea.go.kr/api/{api_key}/C005/json/1/10/BAR_CD={barcode}"
    data = _http_get_json(url, timeout=5.0)

    rows = (data.get("C005") or {}).get("row") or []
    if not isinstance(rows, list):
        return []

    candidates: list[dict[str, Any]] = []
    for item in rows:
        product_name = _as_str(item.get("PRDLST_NM"))
        manufacturer = _as_str(item.get("BSSH_NM"))
        report_no = _as_str(item.get("PRDLST_REPORT_NO"))
        bar_cd = _as_str(item.get("BAR_CD")) or barcode

        candidate_id = make_candidate_id(
            barcode=bar_cd,
            report_no=report_no,
            product_name=product_name,
            manufacturer=manufacturer,
        )

        candidates.append(
            {
                "candidate_id": candidate_id,
                "barcode": bar_cd,
                "product_name": product_name,
                "manufacturer": manufacturer,
                "report_no": report_no,
                "raw": item,
            }
        )

    return candidates


# ─────────────────────────────────────────────
# 4) 후보 자동 선택 (웹 서버 안전, input() 금지)
# ─────────────────────────────────────────────
def choose_best_candidate(
    items: list[dict[str, Any]],
    *,
    preferred_report_no: str | None = None,
    preferred_manufacturer: str | None = None,
    preferred_product_name: str | None = None,
) -> dict[str, Any] | None:
    """
    기존에 input()으로 고르던 흐름을 자동 점수로 대체
    """
    if not items:
        return None

    prn = _as_str(preferred_report_no) if preferred_report_no else ""
    pmf = _as_str(preferred_manufacturer) if preferred_manufacturer else ""
    ppn = _as_str(preferred_product_name) if preferred_product_name else ""

    def score(x: dict[str, Any]) -> int:
        s = 0
        if prn and _as_str(x.get("report_no")) == prn:
            s += 100
        if pmf and pmf in _as_str(x.get("manufacturer")):
            s += 20
        if ppn and ppn in _as_str(x.get("product_name")):
            s += 10
        return s

    return max(items, key=score)


# ─────────────────────────────────────────────
# 5) 영양 조회 (report_no 기반) - “틀 유지 + TODO 채우기”
# ─────────────────────────────────────────────
def get_nutrition_by_report_no(report_no: str) -> dict[str, Any] | None:
    """
    MFDS 식품영양성분DB(FoodNtrCpntDbInfo02)에서 report_no(=ITEM_REPORT_NO)로
    영양성분을 찾는다.

    - input() 금지
    - 외부 API 실패는 UpstreamAPIError raise
    - 결과 없으면 None
    """
    report_no = (report_no or "").strip()
    if not report_no:
        return None

    nutr_key = _require_env("FOOD_NUTR_KEY")

    base_url = (
        "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02"
    )

    # ✅ 네 텍스트 파일 로직은 '이름(FOOD_NM_KR)'로 먼저 후보를 가져오고,
    # ✅ 후보들 중 ITEM_REPORT_NO == report_no 를 찾는 구조야.:contentReference[oaicite:7]{index=7}
    #
    # 여기 함수는 report_no만 받으므로,
    # 1) report_no로 바로 조회가 가능한 파라미터가 "공식적으로" 있는지 확실치 않아서,
    # 2) 텍스트 파일 흐름을 그대로 살려 "넓게 조회 → report_no로 필터"로 구성한다.
    #
    # 다만 이 방식은 FOOD_NM_KR 없이 후보 조회가 어렵다.
    # 그래서 현실적으로는:
    # - 이 함수 시그니처를 (report_no, product_name, manufacturer)로 바꾸거나,
    # - report_no만으로 조회 가능한 다른 엔드포인트/파라미터를 확인해야 한다.
    #
    # ✅ 텍스트 파일 기준 '정확히 동작'하게 하려면 product_name이 필요하다.:contentReference[oaicite:8]{index=8}
    raise NotImplementedError(
        "텍스트 파일 기준 MFDS 영양 조회는 FOOD_NM_KR(제품명)이 필요합니다. "
        "get_nutrient_from_mfds_with_choice(report_no, product_name, manufacturer)를 사용하세요."
    )


# ─────────────────────────────────────────────
# 6) (기존 함수명 호환) MFDS 후보 선택 + 영양 조회
# ─────────────────────────────────────────────
def get_nutrient_from_mfds_with_choice(
    items: list[dict[str, Any]],
    *,
    preferred_report_no: str | None = None,
    preferred_manufacturer: str | None = None,
    preferred_product_name: str | None = None,
) -> dict[str, Any] | None:
    """
    예전에 input()으로 후보를 고르고 영양을 조회했을 가능성이 높은 함수명.
    - 지금은 자동선택(choose_best_candidate)으로 웹 서버 안전하게 동작.
    """
    if not items:
        return None

    best = choose_best_candidate(
        items,
        preferred_report_no=preferred_report_no,
        preferred_manufacturer=preferred_manufacturer,
        preferred_product_name=preferred_product_name,
    )
    if not best:
        return None

    report_no = _as_str(best.get("report_no"))
    if not report_no:
        return None

    return get_nutrition_by_report_no(report_no)


# ─────────────────────────────────────────────
# 7) (기존 형태 유지) 영양 merge/fallback
# ─────────────────────────────────────────────
def merge_nutrients_with_fallback(
    *,
    primary: dict[str, Any] | None,
    fallback: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    primary 우선, 없으면 fallback
    - 기존에 FatSecret/다른 DB를 fallback으로 쓰던 구조를 이어갈 수 있게 유지
    """
    if primary:
        return primary
    return fallback


# ─────────────────────────────────────────────
# 8) (기존 형태 유지) 바코드 → “통합 정보” (제품 + 영양 + 후보)
# ─────────────────────────────────────────────
def get_food_info_from_barcode(
    barcode: str,
    *,
    preferred_report_no: str | None = None,
    preferred_manufacturer: str | None = None,
    preferred_product_name: str | None = None,
) -> dict[str, Any] | None:
    """
    ✅ 반환 규칙
    - 제품 후보 0개면 None
    - 있으면 dict로 반환

    이 함수는 “scan 단계에서 후보를 내려줄지 / 서버에서 자동선택까지 할지”
    둘 다 대응할 수 있게 구성.
    """
    barcode = _as_str(barcode)
    if not barcode:
        return None

    candidates = get_product_info_by_barcode(barcode)
    if not candidates:
        return None

    best = choose_best_candidate(
        candidates,
        preferred_report_no=preferred_report_no,
        preferred_manufacturer=preferred_manufacturer,
        preferred_product_name=preferred_product_name,
    )

    nutrition = None
    if best:
        report_no = _as_str(best.get("report_no"))
        if report_no:
            nutrition = get_nutrition_by_report_no(report_no)

    return {
        "found": True,
        "barcode": barcode,
        "best": best,  # 자동선택 결과(옵션)
        "nutrition": nutrition,  # 있으면 포함
        "candidates": candidates,  # UI에 보여줄 후보 전체
    }


# ─────────────────────────────────────────────
# 9) (프론트/뷰 호환) 후보 dict를 UI용 키로 바꿔주는 헬퍼(선택)
# ─────────────────────────────────────────────
def normalize_candidate_for_ui(c: dict[str, Any]) -> dict[str, Any]:
    """
    views_api.py에서 쓰기 편하게 key를 맞춰줌
    - name/brand/flavor 형태로 통일
    """
    return {
        "candidate_id": _as_str(c.get("candidate_id")),
        "barcode": _as_str(c.get("barcode")),
        "name": _as_str(c.get("product_name") or c.get("name")),
        "brand": _as_str(c.get("manufacturer") or c.get("brand")),
        "flavor": _as_str(c.get("flavor")),
        "report_no": _as_str(c.get("report_no")),
        "raw": c.get("raw", None),
    }
