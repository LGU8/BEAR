import os
import requests
from fatsecret import Fatsecret
from dotenv import load_dotenv
from django.conf import settings

# ================================
# 0. 환경변수 로드
# ================================
load_dotenv()

FOOD_API_KEY = os.getenv("FOOD_API_KEY")  # C005 (바코드 → 제품 기본정보)
FOOD_NUTR_KEY = os.getenv("FOOD_NUTR_KEY")  # 식품영양성분DB
PROCESSED_FOOD_KEY = os.getenv("PROCESSED_FOOD_KEY")  # 전국통합 가공식품 표준데이터

FATSECRET_KEY = os.getenv("FATSECRET_KEY")
FATSECRET_SECRET = os.getenv("FATSECRET_SECRET")

fs = None
if FATSECRET_KEY and FATSECRET_SECRET:
    fs = Fatsecret(FATSECRET_KEY, FATSECRET_SECRET)

if not FOOD_API_KEY:
    raise RuntimeError("FOOD_API_KEY가 .env에 설정되지 않았습니다.")


# ================================
# 1. C005 바코드 → 제품 기본 정보
# ================================
def get_product_info_by_barcode(barcode: str) -> dict | None:
    """
    바코드 → 식약처 C005 API로 제품 기본정보 조회
    """
    url = (
        f"http://openapi.foodsafetykorea.go.kr/api/"
        f"{FOOD_API_KEY}/C005/json/1/10/BAR_CD={barcode}"
    )

    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    data = resp.json()

    print("[API][C005] top keys:", list(data.keys()))
    print("[API][C005] head:", str(data)[:300])

    try:
        items = data["C005"]["row"]
    except KeyError:
        print("[C005] 응답 구조가 다릅니다:", data)
        return None

    if not items:
        print("[C005] 해당 바코드로 조회되는 제품이 없습니다.")
        return None

    item = items[0]

    print("[DEBUG][C005] 최종 URL:", url)
    print("[DEBUG][C005] 첫 row 바코드:", item.get("BAR_CD"))

    return {
        "report_no": item.get("PRDLST_REPORT_NO"),
        "product_name": item.get("PRDLST_NM"),
        "manufacturer": item.get("BSSH_NM"),
        "barcode": item.get("BAR_CD"),
    }


# ================================
# 2. MFDS 식품영양성분DB에서 영양성분 조회
# ================================
def get_nutrient_from_mfds_with_choice(
    report_no: str | None,
    product_name: str | None,
    manufacturer: str | None = None,
) -> dict | None:
    """
    식품영양성분DB(FoodNtrCpntDbInfo02)에서 영양성분 조회.

    흐름:
      1) FOOD_NM_KR(이름)만으로 조회
      2) manufacturer가 있으면 FOOD_NM_KR + MAKER_NM으로도 추가 조회
      3) 두 결과를 ITEM_REPORT_NO 기준으로 합쳐(중복 제거)
      4) 합쳐진 후보에서
         - report_no 자동 매칭 시도
         - 실패 시 사용자에게 번호(1~N) 입력받아 선택
      5) 선택된 item에서 kcal, 탄/단/지/당 추출
    """

    base_url = (
        "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02"
    )

    cleaned_name = product_name.split("(")[0].strip() if product_name else ""

    # -------------------
    # 공통 요청 함수
    # -------------------
    def _request_mfds(use_maker: bool):
        params = {
            "serviceKey": FOOD_NUTR_KEY,
            "type": "json",
            "pageNo": 1,
            "numOfRows": 50,
            "FOOD_NM_KR": cleaned_name,
        }
        if use_maker and manufacturer:
            params["MAKER_NM"] = manufacturer

        resp = requests.get(base_url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        print("[API][MFDS] top keys:", list(data.keys()))
        print("[API][MFDS] head:", str(data)[:300])

        body = data.get("body", {})
        return body.get("items")

    # 1) 이름-only 결과
    items_name_raw = _request_mfds(use_maker=False)
    # 2) 이름+제조사 결과 (제조사가 있을 때만)
    items_maker_raw = _request_mfds(use_maker=True) if manufacturer else None

    # raw → list 변환 함수
    def _normalize_items(items_raw):
        if not items_raw:
            return []
        if isinstance(items_raw, dict):
            item_obj = items_raw.get("item")
            if isinstance(item_obj, list):
                return item_obj
            elif item_obj:
                return [item_obj]
            return []
        return items_raw

    items_name = _normalize_items(items_name_raw)
    items_maker = _normalize_items(items_maker_raw)

    # 3) 두 결과 합치기 (ITEM_REPORT_NO 또는 FOOD_NM_KR 기준으로 중복 제거)
    items: list[dict] = []
    seen_keys = set()

    for it in items_name + items_maker:
        key = it.get("ITEM_REPORT_NO") or it.get("FOOD_NM_KR")
        if not key:
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        items.append(it)

    if not items:
        print("[MFDS] 이름/제조사 기준으로도 후보가 없습니다.")
        return None

    print(f"[MFDS] 최종 후보 {len(items)}건 발견")

    def _normalize_str(s: str | None) -> str:
        return s.strip() if isinstance(s, str) else ""

    # 4-1) report_no 자동 매칭
    selected = None
    if report_no:
        for it in items:
            if _normalize_str(it.get("ITEM_REPORT_NO")) == _normalize_str(report_no):
                selected = it
                print("[MFDS] report_no로 자동 매칭된 항목 발견")
                break

    # 4-2) 자동 매칭 실패 → 사용자 선택
    if selected is None:
        print("\n[MFDS] 여러 개의 후보가 있습니다. 원하는 항목 번호를 선택하세요.")
        for idx, it in enumerate(items, start=1):
            print(
                f"  [{idx}] {it.get('FOOD_NM_KR')} / "
                f"{it.get('MAKER_NM')} / "
                f"ITEM_REPORT_NO={it.get('ITEM_REPORT_NO')}"
            )

        while selected is None:
            try:
                user_input = input(f"번호 입력 (1~{len(items)}, 기본=1): ").strip()
                if user_input == "":
                    choice = 1
                else:
                    choice = int(user_input)

                if 1 <= choice <= len(items):
                    selected = items[choice - 1]
                else:
                    print("범위 밖 번호입니다. 다시 입력해주세요.")
            except ValueError:
                print("숫자를 입력해주세요.")

    if selected is None:
        print("[MFDS] 선택된 항목이 없습니다(내부 오류).")
        return None

    print("\n[MFDS] 최종 선택된 항목:")
    print("  FOOD_NM_KR     :", selected.get("FOOD_NM_KR"))
    print("  MAKER_NM       :", selected.get("MAKER_NM"))
    print("  ITEM_REPORT_NO :", selected.get("ITEM_REPORT_NO"))

    # -------------------
    # 숫자 변환 헬퍼
    # -------------------
    def _to_float(val: str | None):
        if val is None:
            return None
        s = str(val).strip()
        if s == "":
            return None
        try:
            return float(s.replace(",", ""))
        except (TypeError, ValueError):
            return None

    # 5) 영양성분 파싱
    energy = _to_float(selected.get("AMT_NUM1"))
    carb = _to_float(selected.get("AMT_NUM6"))
    protein = _to_float(selected.get("AMT_NUM3"))
    fat = _to_float(selected.get("AMT_NUM4"))
    sugar_raw = selected.get("AMT_NUM7") or selected.get("AMT_NUM9")
    sugar = _to_float(sugar_raw)

    return {
        "energy_kcal": energy,
        "carb_g": carb,
        "protein_g": protein,
        "fat_g": fat,
        "sugar_g": sugar,
        "nutrient_source": "mfds_db",
        "mfds_food_name": selected.get("FOOD_NM_KR"),
        "mfds_maker_name": selected.get("MAKER_NM"),
        "mfds_report_no": selected.get("ITEM_REPORT_NO"),
    }


# ================================
# 3. 전국통합 가공식품 영양성분
# ================================
def get_nutrients_from_processed_korea(
    product_name: str,
    manufacturer: str | None = None,
) -> dict | None:
    """
    전국통합식품영양성분정보(가공식품) 표준데이터 API에서
    이름(foodNm) 기반으로 영양성분 조회

    - 현재는 SERVICE KEY 등록 문제로 실패할 수 있음
    """

    if not PROCESSED_FOOD_KEY:
        print("[PROC] PROCESSED_FOOD_KEY 미설정")
        return None

    base_url = "http://api.data.go.kr/openapi/tn_pubr_public_nutri_process_info_api"
    cleaned_name = product_name.split("(")[0].strip() if product_name else ""

    params = {
        "serviceKey": PROCESSED_FOOD_KEY,
        "page": 1,
        "perPage": 50,
        "type": "json",
        "foodNm": cleaned_name,
    }
    if manufacturer:
        params["mfrNm"] = manufacturer

    resp = requests.get(base_url, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()

    print("[DEBUG][PROC] raw:", data)

    # 공공데이터포털 공통 구조: response.header / response.body
    response_obj = data.get("response") or {}
    header = response_obj.get("header") or {}

    result_code = header.get("resultCode")
    result_msg = header.get("resultMsg")

    if result_code and result_code != "00":
        print(f"[PROC] API 오류: {result_code} / {result_msg}")
        return None

    body = response_obj.get("body") or {}
    items = body.get("items")

    if not items:
        print("[PROC] items 없음 (검색 결과 0건)")
        return None

    if isinstance(items, dict):
        items_list = [items]
    else:
        items_list = list(items)

    selected = items_list[0]

    def _to_float(val):
        if val in (None, ""):
            return None
        try:
            return float(str(val).replace(",", ""))
        except (TypeError, ValueError):
            return None

    return {
        "energy_kcal": _to_float(selected.get("enerc")),
        "carb_g": _to_float(selected.get("chocdf")),
        "protein_g": _to_float(selected.get("prot")),
        "fat_g": _to_float(selected.get("fatce")),
        "sugar_g": _to_float(selected.get("sugar")),
        "nutrient_source": "processed_korea",
    }


# ================================
# 4. FatSecret fallback
# ================================
def get_nutrients_from_fatsecret(product_name: str) -> dict | None:
    """
    FatSecret API로 영양성분 조회 (fallback 용)
    """
    if fs is None:
        print("[FatSecret] KEY/SECRET 미설정으로 사용 불가")
        return None

    try:
        search_results = fs.foods_search(product_name)
    except Exception as e:
        print("[FatSecret] 검색 오류:", e)
        return None

    if not search_results:
        print("[FatSecret] 검색 결과 없음")
        return None

    food_id = search_results[0]["food_id"]
    details = fs.food_get(food_id)
    serving = details.get("servings", {}).get("serving", {})

    def _to_float(val):
        if val in (None, ""):
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    return {
        "energy_kcal": _to_float(serving.get("calories")),
        "carb_g": _to_float(serving.get("carbohydrate")),
        "protein_g": _to_float(serving.get("protein")),
        "fat_g": _to_float(serving.get("fat")),
        "sugar_g": _to_float(serving.get("sugar")),
        "nutrient_source": "fatsecret",
    }


# ================================
# 5. 여러 영양 dict를 필드별로 병합
# ================================
def merge_nutrients_with_fallback(*sources: dict | None) -> dict | None:
    """
    sources: mfds, processed_korea, fatsecret 처럼
             영양 dict 또는 None 이 들어오는 구조.

    각 필드별로:
      - None 이나 0 이면 다음 소스 값 확인
      - 세 소스 모두 None 또는 0 이면 0으로 확정
    """
    valid_sources = [s for s in sources if s]
    if not valid_sources:
        return None

    keys = ["energy_kcal", "carb_g", "protein_g", "fat_g", "sugar_g"]
    merged: dict = {}

    for key in keys:
        chosen = None
        has_zero = False

        for src in valid_sources:
            v = src.get(key)

            if v is None:
                continue

            if v == 0 or v == 0.0:
                if chosen is None:
                    chosen = 0.0
                has_zero = True
                continue

            chosen = v
            break

        if chosen is None and has_zero:
            chosen = 0.0

        merged[key] = chosen

    for src in valid_sources:
        if src.get("nutrient_source"):
            merged["nutrient_source"] = src["nutrient_source"]
            break

    return merged


# ================================
# 6. 바코드 → 최종 음식+영양정보
# ================================
def get_food_info_from_barcode(barcode: str) -> dict | None:
    product = get_product_info_by_barcode(barcode)
    if not product:
        return None

    report_no = product["report_no"]
    product_name = product["product_name"]
    manufacturer = product["manufacturer"]

    print("\n=== C005 제품 기본 정보 ===")
    print("품목제조번호:", report_no)
    print("제품명      :", product_name)
    print("제조사      :", manufacturer)
    print("바코드      :", product["barcode"])

    # 1순위: MFDS (사용자 선택 + report_no 매칭)
    mfds_nutr = get_nutrient_from_mfds_with_choice(
        report_no=report_no,
        product_name=product_name,
        manufacturer=manufacturer,
    )

    # 2순위: 가공식품 표준데이터 (이름 기준)
    processed_nutr = get_nutrients_from_processed_korea(
        product_name=product_name,
        manufacturer=manufacturer,
    )

    # 3순위: FatSecret
    fatsecret_nutr = get_nutrients_from_fatsecret(product_name)

    # 필드별 병합
    nutrients = merge_nutrients_with_fallback(
        mfds_nutr,
        processed_nutr,
        fatsecret_nutr,
    )

    if not nutrients:
        return {**product, "nutrients": None}

    result = {**product, **nutrients}

    if mfds_nutr:
        if mfds_nutr.get("mfds_food_name"):
            result["product_name_mfds"] = mfds_nutr["mfds_food_name"]
        if mfds_nutr.get("mfds_maker_name"):
            result["manufacturer_mfds"] = mfds_nutr["mfds_maker_name"]
        if mfds_nutr.get("mfds_report_no"):
            result["report_no_mfds"] = mfds_nutr["mfds_report_no"]

    return result
