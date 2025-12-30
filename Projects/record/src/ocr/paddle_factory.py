from __future__ import annotations

from typing import Optional, Any, Dict
import platform
from paddleocr import PaddleOCR

_ocr_instance: Optional[PaddleOCR] = None


def get_ocr_fast() -> PaddleOCR:
    """
    목표: 1분 내외를 위해 '가벼운 설정'을 기본으로.
    - orientation/angle classifier 계열 기능은 OFF
    - batch size는 약간 올려서 인식 속도 개선
    - Windows/Intel에서는 mkldnn(onednn) ON이 유리한 경우가 많음
    """
    global _ocr_instance
    if _ocr_instance is not None:
        return _ocr_instance

    sys = platform.system().lower()

    # mac에서는 mkldnn가 이득이 없거나 이슈가 나는 경우가 많아 OFF
    enable_mkldnn = False if "darwin" in sys else True

    base_kwargs: Dict[str, Any] = dict(
        lang="korean",
        enable_mkldnn=enable_mkldnn,
    )

    # PaddleOCR 버전에 따라 파라미터 이름이 바뀌어도 죽지 않도록 후보를 순차 적용
    optional_candidates = [
        # 최신 계열(권장)
        dict(use_textline_orientation=False),
        dict(use_angle_cls=False),  # 구버전 호환
    ]

    # 속도에 큰 영향 있는 옵션(버전별 키가 다름)
    speed_candidates = [
        dict(text_det_limit_side_len=1280),  # 최신
        dict(det_limit_side_len=1280),  # 구버전
        dict(text_recognition_batch_size=8),  # 최신
        dict(rec_batch_num=8),  # 구버전
    ]

    kwargs = dict(base_kwargs)

    # 1) orientation 옵션
    for opt in optional_candidates:
        try:
            _ocr_instance = PaddleOCR(**kwargs, **opt)
            break
        except ValueError:
            continue
    if _ocr_instance is None:
        _ocr_instance = PaddleOCR(**kwargs)

    # 2) speed 옵션은 생성 후 attribute로 못 바꾸는 경우가 많아서
    #    - 가능하면 재생성하되, 실패하면 그냥 진행
    #    (환경마다 PaddleOCR 내부 파라미터 처리 방식이 달라 안전하게 try)
    try:
        # 재생성: 가능한 옵션만 모아서 생성 시에 주입
        merged = dict(kwargs)
        # 현재 인스턴스에 성공했던 orientation 옵션을 최대한 반영
        # (우리는 use_textline_orientation / use_angle_cls 둘 중 하나만 성공했을 가능성)
        # -> 여기서는 둘 다 시도 가능한 형태로 넣고 실패 시 fallback
        merged_try = [
            dict(merged, use_textline_orientation=False),
            dict(merged, use_angle_cls=False),
            dict(merged),
        ]
        speed_opts = {}
        # speed 후보를 하나씩 합치되, Unknown argument면 생성에서 터지므로 조심
        # -> 생성 시도 자체를 3~4회로 제한
        for k, v in [
            ("text_det_limit_side_len", 1280),
            ("det_limit_side_len", 1280),
            ("text_recognition_batch_size", 8),
            ("rec_batch_num", 8),
        ]:
            speed_opts[k] = v

        for base in merged_try:
            try:
                _ocr_instance = PaddleOCR(**base, **speed_opts)
                break
            except ValueError:
                continue
    except Exception:
        pass

    return _ocr_instance


def ocr_call(ocr: PaddleOCR, img_bgr) -> Any:
    """
    PaddleOCR API 변화:
    - 어떤 버전은 ocr.ocr(img) 사용
    - 어떤 버전은 내부적으로 predict로 redirect
    -> 여기서는 'img만' 넣는 기본 호출만 사용(kw det/rec/cls 넣지 않음)
    """
    return ocr.ocr(img_bgr)
