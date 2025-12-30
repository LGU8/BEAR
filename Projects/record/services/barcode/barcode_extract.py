import cv2
from pathlib import Path


def read_barcode_from_image(image_path: str) -> list[str]:
    """
    한 장의 이미지에서 바코드 숫자(EAN-13 등)를 읽어서 리스트로 반환
    """
    img = cv2.imread(image_path)

    if img is None:
        print(f"[ERROR] 이미지를 읽을 수 없습니다: {image_path}")
        return []

    detector = cv2.barcode_BarcodeDetector()

    # ─────────────────────────────────────────
    # 1) OpenCV 버전에 따라 반환값 형태가 제각각이라
    #    어떤 형태든 안전하게 풀어내는 로직
    # ─────────────────────────────────────────
    result = detector.detectAndDecode(img)
    print(f"[DEBUG] raw result for {image_path}:", result, "len =", len(result))

    # 기본 초기값
    decoded_info = []
    decoded_type = []
    points = None

    # 튜플/리스트가 아닌 이상하다 싶으면 바로 종료
    if not isinstance(result, (tuple, list)):
        print(f"[ERROR] 예상치 못한 반환 타입: {type(result)}")
        return []

    # 길이별로 최대한 맞춰보기
    if len(result) == 4:
        retval, decoded_info, decoded_type, points = result
    elif len(result) == 3:
        a, b, c = result

        if isinstance(a, (list, tuple, str, bytes)):
            decoded_info = a
            decoded_type = b
            points = c
        else:
            decoded_info = b
            decoded_type = c
    elif len(result) == 2:
        decoded_info, decoded_type = result
    elif len(result) == 1:
        decoded_info = result[0]
    else:
        print(f"[ERROR] 예상치 못한 반환 길이: {len(result)}")
        return []

    # ─────────────────────────────────────────
    # 2) decoded_info / decoded_type 을
    #    '항상 리스트' 형태로 정규화
    # ─────────────────────────────────────────
    if isinstance(decoded_info, (str, bytes)):
        decoded_info = [decoded_info]
    elif decoded_info is None:
        decoded_info = []

    if isinstance(decoded_type, (str, bytes)):
        decoded_type = [decoded_type]
    elif decoded_type is None:
        decoded_type = []

    if len(decoded_type) != len(decoded_info):
        decoded_type = ["UNKNOWN"] * len(decoded_info)

    if not decoded_info:
        print(f"[INFO] 바코드를 찾지 못했습니다: {image_path}")
        return []

    # ─────────────────────────────────────────
    # 3) 실제 바코드 문자열 필터링
    # ─────────────────────────────────────────
    results = []
    for data, t in zip(decoded_info, decoded_type):
        if not data:
            continue

        data_str = str(data).strip()

        if len(data_str) == 13 and data_str.isdigit():
            results.append(data_str)
            print(f"[DETECT] {image_path} -> {data_str} (type={t})")
        else:
            print(f"[SKIP] {image_path} -> {data_str} (len={len(data_str)}, type={t})")

    return results


def main():
    import sys

    # 인자로 이미지 파일을 넘긴 경우: python barcode2.py IMG_5293.png IMG_5294.png ...
    if len(sys.argv) >= 2:
        image_files = sys.argv[1:]
    else:
        # 인자가 없으면 경고만 띄우고 종료하거나,
        # 혹은 Path('.')에서 자동 탐색을 해도 됨
        print("사용법: python barcode2.py <이미지파일1> [이미지파일2 ...]")
        return

    all_results = []

    for img_path in image_files:
        if not Path(img_path).exists():
            print(f"[WARN] 파일이 없습니다: {img_path}")
            continue

        codes = read_barcode_from_image(img_path)
        all_results.extend([(img_path, code) for code in codes])

    print("\n=== 최종 결과 ===")
    if not all_results:
        print("어떤 이미지에서도 13자리 바코드를 찾지 못했습니다.")
    else:
        for img_path, code in all_results:
            print(f"{img_path}: {code}")


if __name__ == "__main__":
    main()
