"""
nutrition_ocr_fast_v2.py

개선점:
- Multi-pass OCR 제거: 이미지당 OCR 1회 수행 (실패시 회전 후 1회 더)
- 컨투어 기반 ROI 탐색 로직 제거 (OCR 좌표 기반 클러스터링으로 대체)
- 불필요한 이미지 전처리(CLAHE 등) 최소화하여 파이프라인 단축
- 예상 속도: 이미지당 1~3초 (CPU/MPS 기준)
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any
import time

import cv2
import numpy as np
import re
import json
from paddleocr import PaddleOCR

# =========================================================
# 0. 설정 및 상수
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
IMG_DIR = BASE_DIR / "assets" / "image_data"
DEBUG_DIR = BASE_DIR / "debug_fast_ocr"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

# OCR 시 입력 이미지의 최대 해상도 (속도 조절의 핵심)
# 너무 크면 느려지고, 너무 작으면 인식이 안됨. 1280~1500 정도가 적당.
MAX_IMAGE_SIZE = 1280

KEYWORD_WEIGHTS = {
    "나트륨": 3,
    "탄수화물": 3,
    "당류": 2,
    "지방": 2,
    "트랜스지방": 3,
    "포화지방": 3,
    "콜레스테롤": 3,
    "단백질": 3,
    "칼로리": 2,
    "kcal": 2,
    "영양정보": 5,
    "총내용량": 3,
}

# =========================================================
# 1. OCR 인스턴스 (최적화 옵션 적용)
# =========================================================

_ocr_instance: Optional[PaddleOCR] = None


def get_ocr() -> PaddleOCR:
    global _ocr_instance
    if _ocr_instance is not None:
        return _ocr_instance

    # Mac M1/M2 등에서는 mkldnn 끄는 게 나을 수 있음
    # use_angle_cls=True를 사용하여 180도 뒤집힌 텍스트 자동 보정
    _ocr_instance = PaddleOCR(
        lang="korean", use_angle_cls=True, show_log=False, enable_mkldnn=False
    )
    return _ocr_instance


# =========================================================
# 2. 유틸리티: 리사이징 및 시각화
# =========================================================


def resize_keep_ratio(img: np.ndarray, max_side: int) -> Tuple[np.ndarray, float]:
    h, w = img.shape[:2]
    if max(h, w) <= max_side:
        return img, 1.0

    scale = max_side / float(max(h, w))
    new_w, new_h = int(w * scale), int(h * scale)
    img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    return img_resized, scale


def save_debug_image(img: np.ndarray, name: str):
    path = DEBUG_DIR / name
    cv2.imwrite(str(path), img)


# =========================================================
# 3. 핵심 로직: 좌표 기반 영양정보 영역 추출
# =========================================================


def filter_nutrition_area(
    ocr_results: List[Any], img_w: int, img_h: int
) -> Tuple[List[str], float]:
    """
    전체 OCR 결과에서 '영양정보' 관련 키워드가 밀집된 영역(ROI)을 찾고,
    해당 영역 안의 텍스트만 필터링하여 반환합니다.
    """
    if not ocr_results:
        return [], 0.0

    # 1. 키워드 박스 수집
    keyword_boxes = []
    total_score = 0.0

    # PaddleOCR 결과 포맷 정규화 (box, (text, score))
    parsed_items = []
    for line in ocr_results:
        # line 구조: [[x1,y1, x2,y2, ...], ("text", score)]
        box = np.array(line[0], dtype=np.float32)
        text = line[1][0]
        score = line[1][1]

        parsed_items.append((box, text, score))

        # 정규화된 텍스트로 키워드 매칭
        norm_text = text.replace(" ", "").replace(",", "")
        for kw, weight in KEYWORD_WEIGHTS.items():
            if kw in norm_text:
                keyword_boxes.append(box)
                total_score += weight
                break  # 한 텍스트에 여러 키워드 있어도 한번만

    # 키워드가 너무 적으면 유효한 영양정보가 아닐 확률 높음
    if len(keyword_boxes) < 3:
        # fallback: 전체 텍스트 반환 (혹시 모르니)
        all_texts = [p[1] for p in parsed_items]
        return all_texts, total_score

    # 2. 키워드들의 외곽 박스(ROI) 계산
    points = np.concatenate(keyword_boxes, axis=0)
    x1 = np.min(points[:, 0])
    y1 = np.min(points[:, 1])
    x2 = np.max(points[:, 0])
    y2 = np.max(points[:, 1])

    # 3. ROI 확장 (Margin 추가)
    # 영양정보 표는 키워드 옆에 숫자가 있으므로, 좌우상하로 넉넉히 확장해야 함
    w_box = x2 - x1
    h_box = y2 - y1

    margin_x = w_box * 0.2  # 좌우 20% 확장
    margin_y = h_box * 0.1  # 상하 10% 확장

    roi_x1 = max(0, x1 - margin_x)
    roi_y1 = max(0, y1 - margin_y)
    roi_x2 = min(img_w, x2 + margin_x)
    roi_y2 = min(img_h, y2 + margin_y)

    # 4. ROI 안에 포함(또는 교차)되는 텍스트만 선별 + 줄 단위 정렬
    filtered_items = []
    for box, text, score in parsed_items:
        bx1, by1 = np.min(box[:, 0]), np.min(box[:, 1])
        bx2, by2 = np.max(box[:, 0]), np.max(box[:, 1])

        # 중심점이 ROI 안에 있는지 확인
        cx = (bx1 + bx2) / 2
        cy = (by1 + by2) / 2

        if (roi_x1 <= cx <= roi_x2) and (roi_y1 <= cy <= roi_y2):
            filtered_items.append((cy, cx, text))  # y좌표 기준으로 정렬하기 위해

    # y축(줄) 기준으로 정렬 후 x축 정렬 (읽는 순서)
    # 간단하게 y좌표로 정렬 (줄바꿈 처리는 정규식 단계에서 해결하도록 텍스트 나열)
    filtered_items.sort(key=lambda x: x[0])

    final_texts = [item[2] for item in filtered_items]
    return final_texts, total_score


# =========================================================
# 4. 기존 정규화 로직 (그대로 사용)
# =========================================================

# (기존 코드의 normalize_korean_nutrition_text, parse_nutrition_kor_v1,
#  build_schema_v1 함수들은 로직이 훌륭하므로 그대로 사용합니다.
#  이 부분은 질문자님의 코드를 복사해서 쓰시면 됩니다.
#  여기서는 지면상 핵심 함수만 간략히 포함합니다.)


def normalize_text_fast(text_list: List[str]) -> str:
    # 리스트를 하나의 문자열로 합침
    full_text = " ".join(text_list)

    # 1. 기본 오타 교정
    full_text = full_text.replace(" ", "").replace(
        ",", "."
    )  # 일단 공백 제거 후 필요시 복구

    # 여기서부터는 정규식으로 끊어내야 함.
    # 질문자님의 normalize_korean_nutrition_text 로직을 그대로 쓰되,
    # 입력이 List[str]에서 합쳐진 str이 되었다는 점만 다름.
    # (실제 구현시에는 질문자님의 정규화 함수 전체를 복붙하세요)

    # 간이 구현 예시
    t = full_text
    t = t.replace("kcal", " kcal ")
    t = t.replace("mg", " mg ")
    t = t.replace("g", " g ")
    t = re.sub(r"(탄수화물|당류|지방|단백질|나트륨)", r" \1 ", t)
    return t


# =========================================================
# 5. 메인 파이프라인 (One-Pass)
# =========================================================


def process_image_fast(img_path: Path) -> Dict[str, Any]:
    start_time = time.time()

    # 1. 이미지 로드
    img_bgr = cv2.imread(str(img_path))
    if img_bgr is None:
        return {"error": "Load Failed"}

    h, w = img_bgr.shape[:2]
    ocr = get_ocr()

    # 2. 리사이징 (속도 최적화 핵심)
    # 4000px 짜리 이미지를 넣으면 매우 느림 -> 1280px 수준으로 줄임
    img_resized, scale = resize_keep_ratio(img_bgr, MAX_IMAGE_SIZE)
    rh, rw = img_resized.shape[:2]

    # 3. 1차 OCR 수행 (0도 기준)
    # cls=True로 설정하면 180도 뒤집힌건 알아서 잡음
    results = ocr.ocr(img_resized, cls=True)
    ocr_result_0 = results[0] if results else []

    # 4. 결과 분석 (0도에서 영양성분 키워드가 발견되는가?)
    texts_0, score_0 = filter_nutrition_area(ocr_result_0, rw, rh)

    final_texts = texts_0
    orientation = "0"

    # 5. 키워드가 거의 없다면 90도 회전해서 2차 시도 (Fallback)
    # 세로로 찍은 사진 대응
    if score_0 < 10.0:  # 임계값 (키워드 가중치 합)
        print(f"  [INFO] Low score ({score_0}), trying rotation...")
        img_rot = cv2.rotate(img_resized, cv2.ROTATE_90_CLOCKWISE)
        results_90 = ocr.ocr(img_rot, cls=True)
        ocr_result_90 = results_90[0] if results_90 else []
        texts_90, score_90 = filter_nutrition_area(
            ocr_result_90, rh, rw
        )  # w, h 반전 주의

        if score_90 > score_0:
            final_texts = texts_90
            orientation = "90"
            print(f"  [INFO] Rotation successful (Score: {score_90})")

    # 6. 텍스트 후처리 (정규화 -> 파싱)
    # 질문자님의 기존 정규화 함수 사용 (여기서는 단순화)
    # raw_string = " ".join(final_texts)
    # normalized = normalize_korean_nutrition_text(raw_string)
    # parsed = parse_nutrition_kor_v1(normalized)

    # 데모용 단순 결과
    result_text = " ".join(final_texts)

    elapsed = time.time() - start_time

    return {
        "filename": img_path.name,
        "time_sec": round(elapsed, 2),
        "orientation": orientation,
        "text_preview": result_text[:100] + "...",
        "full_text": result_text,
        # "parsed": parsed  <-- 여기에 기존 파싱 결과 넣기
    }


# =========================================================
# 6. 실행
# =========================================================

if __name__ == "__main__":
    # 테스트 파일 리스트
    test_files = sorted(list(IMG_DIR.glob("*.jpg")) + list(IMG_DIR.glob("*.png")))

    print(f"Found {len(test_files)} images.")

    for img_p in test_files:
        print(f"Processing {img_p.name}...")
        try:
            res = process_image_fast(img_p)
            print(f" -> Done in {res['time_sec']}s | Orient: {res['orientation']}")
            # print(f" -> Text: {res['text_preview']}")
        except Exception as e:
            print(f" -> Error: {e}")
