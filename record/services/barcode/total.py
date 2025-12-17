# barcode2.py 에서 바코드 인식 함수 가져오기
from .barcode_extract import read_barcode_from_image

# test5.py 에서 바코드 → 음식/영양정보 함수 가져오기
from .mapping_code import get_product_info_by_barcode


def run_barcode_pipeline(image_path: str):
    barcode = read_barcode_from_image(image_path)
    candidates = get_product_info_by_barcode(barcode)
    return barcode, candidates
