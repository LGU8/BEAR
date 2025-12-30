from __future__ import annotations

import cv2
import numpy as np
from typing import Tuple


def resize_max_side(
    img_bgr: np.ndarray, max_side: int = 1600
) -> Tuple[np.ndarray, float]:
    h, w = img_bgr.shape[:2]
    scale = 1.0
    if max(h, w) > max_side:
        scale = max_side / float(max(h, w))
        img_bgr = cv2.resize(
            img_bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA
        )
    return img_bgr, scale


def deskew_light(img_bgr: np.ndarray) -> np.ndarray:
    """
    deskew는 비용이 큼. 기본 OFF를 추천.
    정말 필요할 때만 쓰도록 pipeline에서 옵션 처리.
    """
    return img_bgr
