# record/services/barcode/total.py
from .barcode_extract import read_barcode_from_image
from .mapping_code import get_product_info_by_barcode


def run_barcode_pipeline(image_path: str):
    """
    이미지 → 바코드 추출 → C005로 제품 후보 조회
    반환:
      (barcode: str, candidates: list[dict])
    """
    barcodes = read_barcode_from_image(image_path)  # list[str]

    barcode = ""
    if isinstance(barcodes, (list, tuple)) and barcodes:
        barcode = str(barcodes[0]).strip()
    else:
        barcode = str(barcodes).strip() if barcodes else ""

    if not barcode:
        return "", []  # ✅ candidates는 list로 통일

    # ✅ mapping_code는 항상 list 반환으로 통일
    candidates = get_product_info_by_barcode(barcode)
    if not candidates:
        candidates = []

    return barcode, candidates
