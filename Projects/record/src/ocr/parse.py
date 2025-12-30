from __future__ import annotations

from typing import Any, List, Tuple
import numpy as np


def parse_ocr_result(
    result: Any,
    score_thresh: float = 0.6,
) -> Tuple[List[str], List[np.ndarray], List[float]]:
    if not result:
        return [], [], []

    texts: List[str] = []
    boxes: List[np.ndarray] = []
    scores: List[float] = []

    first = result[0]

    # dict 포맷
    if isinstance(first, dict) and "rec_texts" in first:
        item = first
        rec_texts = item.get("rec_texts", [])
        rec_scores = item.get("rec_scores", [])
        rec_boxes = item.get("rec_boxes", [])

        if isinstance(rec_texts, np.ndarray):
            rec_texts = rec_texts.tolist()
        if isinstance(rec_scores, np.ndarray):
            rec_scores = rec_scores.tolist()
        if isinstance(rec_boxes, np.ndarray):
            rec_boxes = rec_boxes.tolist()

        for t, s, b in zip(rec_texts, rec_scores, rec_boxes):
            t = (t or "").strip()
            s = float(s)
            if not t or s < score_thresh:
                continue
            texts.append(t)
            boxes.append(np.array(b))
            scores.append(s)

    # list 포맷
    elif isinstance(first, list):
        for line in result:
            for box, (t, s) in line:
                t = (t or "").strip()
                s = float(s)
                if not t or s < score_thresh:
                    continue
                texts.append(t)
                boxes.append(np.array(box))
                scores.append(s)

    return texts, boxes, scores


def group_into_lines(
    texts: List[str],
    boxes: List[np.ndarray],
    scores: List[float],
    score_thresh: float = 0.6,
) -> List[str]:
    if not texts:
        return []

    items = []
    for t, b, s in zip(texts, boxes, scores):
        if not t or s < score_thresh:
            continue
        b = np.array(b).reshape(-1, 2)
        xs, ys = b[:, 0], b[:, 1]
        x1, x2 = float(xs.min()), float(xs.max())
        y1, y2 = float(ys.min()), float(ys.max())
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        h = y2 - y1
        items.append((t.strip(), cx, cy, h))

    if not items:
        return []

    heights = [it[3] for it in items]
    median_h = float(np.median(heights)) if heights else 40.0
    line_threshold = max(18.0, median_h * 0.7)

    items.sort(key=lambda it: (it[2], it[1]))  # (cy, cx)

    lines: List[str] = []
    cur_y = None
    cur_tokens: List[str] = []

    for t, cx, cy, h in items:
        if cur_y is None:
            cur_y = cy
            cur_tokens = [t]
        else:
            if abs(cy - cur_y) <= line_threshold:
                cur_tokens.append(t)
            else:
                lines.append(" ".join(cur_tokens))
                cur_y = cy
                cur_tokens = [t]

    if cur_tokens:
        lines.append(" ".join(cur_tokens))

    return lines
