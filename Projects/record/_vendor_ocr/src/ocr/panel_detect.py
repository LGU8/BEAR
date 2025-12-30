from __future__ import annotations

from typing import Optional, Tuple, List
import numpy as np
import cv2

from src.ocr.paddle_factory import ocr_call
from src.ocr.parse import parse_ocr_result
from src.ocr.preprocess import resize_max_side

PANEL_KEYWORDS = [
    "영양정보",
    "영양성분",
    "총내용량",
    "총 내용량",
    "1일 영양성분",
    "기준치에 대한 비율",
    "기준치에대한비율",
    "나트륨",
    "탄수화물",
    "당류",
    "지방",
    "포화지방",
    "트랜스지방",
    "콜레스테롤",
    "단백질",
    "kcal",
    "열량",
]


def _is_kw(text: str) -> bool:
    t = (text or "").replace(" ", "")
    for kw in PANEL_KEYWORDS:
        if kw.replace(" ", "") in t:
            return True
    if "kcal" in t.lower():
        return True
    return False


def find_panel_bbox_fast(
    img_bgr: np.ndarray, ocr, score_thresh: float = 0.5
) -> Optional[Tuple[int, int, int, int]]:
    """
    빠른 ROI:
    - img를 max_side=1000 정도로 축소 후 OCR 1회
    - 영양 키워드 bbox들을 합쳐 ROI 생성
    - 키워드가 너무 적으면 None -> contour fallback을 pipeline에서 사용
    """
    h, w = img_bgr.shape[:2]
    img_small, scale = resize_max_side(img_bgr, max_side=1000)

    raw = ocr_call(ocr, img_small)
    texts, boxes, scores = parse_ocr_result(raw, score_thresh=score_thresh)
    if not texts:
        return None

    selected = []
    for t, box, s in zip(texts, boxes, scores):
        if s < score_thresh:
            continue
        if not _is_kw(t):
            continue
        b = np.array(box, dtype=np.float32).reshape(-1, 2)
        if scale != 1.0:
            b = b / scale
        xs, ys = b[:, 0], b[:, 1]
        selected.append([xs.min(), ys.min(), xs.max(), ys.max()])

    if len(selected) < 2:
        return None

    selected = np.array(selected, dtype=np.float32)
    x1 = float(selected[:, 0].min())
    y1 = float(selected[:, 1].min())
    x2 = float(selected[:, 2].max())
    y2 = float(selected[:, 3].max())

    mx = (x2 - x1) * 0.15
    my = (y2 - y1) * 0.15

    x1 = max(0, int(x1 - mx))
    y1 = max(0, int(y1 - my))
    x2 = min(w, int(x2 + mx))
    y2 = min(h, int(y2 + my))

    bw = max(1, x2 - x1)
    bh = max(1, y2 - y1)

    if bw * bh < 0.01 * w * h:
        return None

    return (x1, y1, bw, bh)


def crop_with_margin(
    img_bgr: np.ndarray, bbox: Tuple[int, int, int, int], margin_ratio: float = 0.10
) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    x, y, bw, bh = bbox
    mx = int(bw * margin_ratio)
    my = int(bh * margin_ratio)
    x1 = max(0, x - mx)
    y1 = max(0, y - my)
    x2 = min(w, x + bw + mx)
    y2 = min(h, y + bh + my)
    return img_bgr[y1:y2, x1:x2].copy()


def find_panel_bbox_by_contour(img_bgr: np.ndarray) -> Tuple[int, int, int, int]:
    """
    contour는 OCR 없이도 가능(빠름).
    실패하면 전체 bbox 반환.
    """
    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch
        if area < 0.02 * w * h:
            continue
        aspect = cw / (ch + 1e-6)
        if aspect < 1.0:
            continue
        candidates.append((x, y, cw, ch, area))

    if not candidates:
        return (0, 0, w, h)

    best = max(candidates, key=lambda t: t[4])
    return (int(best[0]), int(best[1]), int(best[2]), int(best[3]))
