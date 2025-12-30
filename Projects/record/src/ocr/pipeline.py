from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import cv2
import numpy as np

from src.utils.timeutil import Timer
from src.ocr.paddle_factory import get_ocr_fast, ocr_call
from src.ocr.preprocess import resize_max_side
from src.ocr.panel_detect import (
    find_panel_bbox_fast,
    find_panel_bbox_by_contour,
    crop_with_margin,
)
from src.ocr.parse import parse_ocr_result, group_into_lines
from src.ocr.normalize import normalize_korean_nutrition_text
from src.ocr.nutrition_parse import parse_nutrition_kor_v1
from src.ocr.schema import build_schema_v1


def quality_score(normalized_text: str) -> int:
    """
    간단/빠른 품질 스코어(키워드 히트 수)
    """
    txt = (normalized_text or "").replace(" ", "")
    kw = [
        "영양정보",
        "총내용량",
        "나트륨",
        "탄수화물",
        "당류",
        "지방",
        "단백질",
        "콜레스테롤",
        "트랜스지방",
        "포화지방",
        "kcal",
    ]
    return sum(1 for k in kw if k in txt)


def ocr_once(
    img_bgr: np.ndarray, ocr, score_thresh: float
) -> Tuple[str, Dict[str, Any]]:
    raw = ocr_call(ocr, img_bgr)
    texts, boxes, scores = parse_ocr_result(raw, score_thresh=score_thresh)
    lines = group_into_lines(texts, boxes, scores, score_thresh=score_thresh)
    raw_text = "\n".join(lines) if lines else ""
    norm = normalize_korean_nutrition_text(raw_text) if raw_text else ""
    q = {
        "n_lines": len(lines),
        "kw_hits": quality_score(norm),
    }
    return norm, {"raw_text": raw_text, "quality": q}


def run_ocr_pipeline(
    img_bgr: np.ndarray,
    score_thresh: float = 0.6,
    max_side: int = 1600,
    try_rotate_if_low: bool = True,
    rotate_kw_threshold: int = 4,  # ROI 결과 키워드 히트가 이 값보다 작으면 rotation 시도
    do_full_fallback: bool = True,
    full_kw_threshold: int = 4,  # ROI가 낮으면 FULL도 시도(단, 1회만)
) -> Dict[str, Any]:
    """
    속도 설계:
    1) resize(max_side)
    2) ROI bbox 탐지(작은 OCR 1회 + contour fallback)
    3) ROI OCR 1회
    4) (조건부) ROI rotation OCR 1회
    5) (조건부) FULL OCR 1회(그리고 필요시 rotation 1회) -> 아주 제한적으로
    """
    t_all = Timer.start()
    ocr = get_ocr_fast()

    img_rs, _ = resize_max_side(img_bgr, max_side=max_side)

    # ROI bbox
    bbox = find_panel_bbox_fast(img_rs, ocr, score_thresh=0.5)
    if bbox is None:
        bbox = find_panel_bbox_by_contour(img_rs)
    roi_img = crop_with_margin(img_rs, bbox, margin_ratio=0.10)

    # ROI OCR 0도
    t_roi = Timer.start()
    roi_norm0, roi_meta0 = ocr_once(roi_img, ocr, score_thresh)
    roi_kw0 = int((roi_meta0.get("quality") or {}).get("kw_hits", 0))
    roi_best_norm = roi_norm0
    roi_best_meta = {"orientation": "0", **roi_meta0}
    roi_time = t_roi.sec()

    # ROI rotation(조건부)
    if try_rotate_if_low and roi_kw0 < rotate_kw_threshold:
        roi_rot = cv2.rotate(roi_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        roi_norm90, roi_meta90 = ocr_once(roi_rot, ocr, score_thresh)
        roi_kw90 = int((roi_meta90.get("quality") or {}).get("kw_hits", 0))
        if roi_kw90 > roi_kw0:
            roi_best_norm = roi_norm90
            roi_best_meta = {"orientation": "90", **roi_meta90}

    # ROI 파싱
    roi_parsed = parse_nutrition_kor_v1(roi_best_norm) if roi_best_norm else {}
    roi_schema = build_schema_v1(roi_parsed) if roi_parsed else []
    roi_score = float(quality_score(roi_best_norm))

    final_source = "ROI"
    final_norm = roi_best_norm
    final_parsed = roi_parsed
    final_schema = roi_schema
    full_score = 0.0
    full_meta_best = {}

    # FULL fallback(조건부)
    if do_full_fallback and roi_score < full_kw_threshold:
        t_full = Timer.start()
        full_norm0, full_meta0 = ocr_once(img_rs, ocr, score_thresh)
        full_kw0 = int((full_meta0.get("quality") or {}).get("kw_hits", 0))
        full_best_norm = full_norm0
        full_best_meta = {"orientation": "0", **full_meta0}

        if try_rotate_if_low and full_kw0 < rotate_kw_threshold:
            full_rot = cv2.rotate(img_rs, cv2.ROTATE_90_COUNTERCLOCKWISE)
            full_norm90, full_meta90 = ocr_once(full_rot, ocr, score_thresh)
            full_kw90 = int((full_meta90.get("quality") or {}).get("kw_hits", 0))
            if full_kw90 > full_kw0:
                full_best_norm = full_norm90
                full_best_meta = {"orientation": "90", **full_meta90}

        full_parsed2 = parse_nutrition_kor_v1(full_best_norm) if full_best_norm else {}
        full_schema2 = build_schema_v1(full_parsed2) if full_parsed2 else []
        full_score = float(quality_score(full_best_norm))
        full_time = t_full.sec()

        # ROI vs FULL 선택
        if full_score > roi_score:
            final_source = "FULL"
            final_norm = full_best_norm
            final_parsed = full_parsed2
            final_schema = full_schema2
            full_meta_best = {**full_best_meta, "elapsed_sec": full_time}
        else:
            full_meta_best = {**full_best_meta, "elapsed_sec": full_time}
    else:
        full_meta_best = {"skipped": True}

    out = {
        "success": bool((final_norm or "").strip()),
        "final_source": final_source,  # "ROI" / "FULL"
        "final_text": final_norm,  # RAG 투입용
        "parsed_nutrition": final_parsed,
        "schema_v1": final_schema,
        "bbox_roi": {
            "x": int(bbox[0]),
            "y": int(bbox[1]),
            "w": int(bbox[2]),
            "h": int(bbox[3]),
        },
        "debug": {
            "roi_score": float(roi_score),
            "full_score": float(full_score),
            "roi_detail": {**roi_best_meta, "elapsed_sec": float(roi_time)},
            "full_detail": full_meta_best,
            "elapsed_sec_total": float(t_all.sec()),
            "params": {
                "score_thresh": score_thresh,
                "max_side": max_side,
                "try_rotate_if_low": try_rotate_if_low,
                "rotate_kw_threshold": rotate_kw_threshold,
                "do_full_fallback": do_full_fallback,
                "full_kw_threshold": full_kw_threshold,
            },
        },
    }

    if not out["success"]:
        out["error_code"] = "E_EMPTY"

    return out
