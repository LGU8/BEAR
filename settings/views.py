from django.shortcuts import render
from settings.badges import BADGE_MASTER
from datetime import date
from typing import Optional, Dict, Any, List


# ------------------------------------------------------------
# 공통: local 더미 데이터 (나중에 DB에서 그대로 교체)
#  - DB 테이블: CUST_TM, CUS_PROFILE_TS 컬럼명 기준
# ------------------------------------------------------------
def _dummy_user() -> Dict[str, Any]:
    return {
        "cust_id": "1000000001",
        "email": "BEAR@naver.com",
        "created_dt": "20260110",  # YYYYMMDD
        "nickname": "탱이",
    }


def _dummy_profile() -> Dict[str, Any]:
    return {
        "height_cm": 178,
        "weight_kg": 70,
        "gender": "M",          # 'M'/'F'
        "birth_dt": "20010804", # YYYYMMDD

        "Ratio_carb": 3,
        "Ratio_protein": 5,
        "Ratio_fat": 2,         # 합=10

        "activity_level": "3",  # 1~4
        "purpose": "2",         # 1=Diet,2=Main(유지),3=Bulk
    }


def _format_yyyymmdd_to_dots(s: str) -> str:
    if not s or len(s) != 8:
        return ""
    return f"{s[0:4]}.{s[4:6]}.{s[6:8]}"


def _gender_label(gender: str) -> str:
    return "남" if gender == "M" else ("여" if gender == "F" else "")


def _calc_age_from_birth(birth_dt: str) -> Optional[int]:
    """
    birth_dt: 'YYYYMMDD'
    return: 만 나이 (int) or None
    """
    if not birth_dt or len(birth_dt) != 8:
        return None

    try:
        by = int(birth_dt[0:4])
        bm = int(birth_dt[4:6])
        bd = int(birth_dt[6:8])
    except ValueError:
        return None

    today = date.today()
    age = today.year - by
    if (today.month, today.day) < (bm, bd):
        age -= 1
    return age


def _activity_copy(level: str) -> Dict[str, str]:
    """
    S1에서 즉시 보여줄 문구 매핑
    """
    mapping = {
        "1": {"label": "낮음", "desc": "하루 종일 주로 앉아서 생활해요\n주 1~3회 가벼운 운동"},
        "2": {"label": "중간", "desc": "일상 활동이 평균이에요\n주 3회 이상 운동 중이에요"},
        "3": {"label": "높음", "desc": "활동량이 많은 편이에요\n주 5회 이상 운동"},
        "4": {"label": "매우 높음", "desc": "하루종일 활동(육체노동 등)\n매일 운동"},
    }
    return mapping.get(str(level), {"label": "-", "desc": ""})


def _purpose_label(purpose: str) -> str:
    return {"1": "다이어트", "2": "유지", "3": "벌크업"}.get(str(purpose), "-")


def _segments_10(value_0_10: int) -> List[bool]:
    """
    0~10 -> 길이 10의 on/off
    (예: 3이면 True 3개, False 7개)
    """
    v = max(0, min(10, int(value_0_10)))
    return [i < v for i in range(10)]


def _base_ctx(active_tab: str = "") -> Dict[str, Any]:
    user = _dummy_user()
    profile = _dummy_profile()

    # 배지(프로필 이미지)
    profile_badge_id = "DEFAULT"
    profile_badge_img = BADGE_MASTER.get(profile_badge_id, BADGE_MASTER["DEFAULT"])["image"]

    # 화면 표기값
    created_dt_label = _format_yyyymmdd_to_dots(user.get("created_dt"))
    gender_label = _gender_label(profile.get("gender"))

    # 만 나이
    birth_dt = profile.get("birth_dt")
    age = _calc_age_from_birth(birth_dt)

    # preferences (합=10)
    ratio_carb = int(profile.get("Ratio_carb") or 0)
    ratio_protein = int(profile.get("Ratio_protein") or 0)
    ratio_fat = int(profile.get("Ratio_fat") or 0)
    ratio_sum = ratio_carb + ratio_protein + ratio_fat

    # S1: activity/purpose 문구
    activity_level = str(profile.get("activity_level") or "")
    activity_copy = _activity_copy(activity_level)
    purpose = str(profile.get("purpose") or "")
    purpose_label = _purpose_label(purpose)

    # 단위 라벨 (S0/S1 공통으로 쓰기 좋게)
    height_cm = profile.get("height_cm")
    weight_kg = profile.get("weight_kg")
    height_cm_label = f"{int(height_cm)} cm" if height_cm is not None else "-"
    weight_kg_label = f"{int(weight_kg)} kg" if weight_kg is not None else "-"

    return {
        "active_tab": active_tab,

        "profile_badge_img": profile_badge_img,

        # user/profile
        "cust_id": user.get("cust_id"),
        "email": user.get("email"),
        "nickname": user.get("nickname"),
        "created_dt": user.get("created_dt"),
        "created_dt_label": created_dt_label,

        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "height_cm_label": height_cm_label,
        "weight_kg_label": weight_kg_label,

        "gender": profile.get("gender"),
        "gender_label": gender_label,
        "birth_dt": birth_dt,
        "age": age,

        # preferences
        "ratio_carb": ratio_carb,
        "ratio_protein": ratio_protein,
        "ratio_fat": ratio_fat,
        "ratio_sum": ratio_sum,

        # segmented(10칸) - S1에서 바로 사용
        "carb_segments": _segments_10(ratio_carb),
        "protein_segments": _segments_10(ratio_protein),
        "fat_segments": _segments_10(ratio_fat),

        # activity/goal
        "activity_level": activity_level,
        "activity_level_label": activity_copy["label"],
        "activity_level_desc": activity_copy["desc"],
        "purpose": purpose,
        "purpose_label": purpose_label,

        "seg_range": range(1, 11),
    }


# ----------------------------
# Views (S0~S5)
# ----------------------------
def settings_index(request):  # S0
    return render(request, "settings/settings_index.html", _base_ctx(active_tab=""))


def settings_account(request):  # S1
    return render(request, "settings/settings_account.html", _base_ctx(active_tab=""))


def settings_profile_edit(request):  # S2
    return render(request, "settings/settings_profile_edit.html", _base_ctx(active_tab=""))


def settings_preferences_edit(request):  # S3
    return render(request, "settings/settings_preferences_edit.html", _base_ctx(active_tab=""))


def settings_activity_goal_edit(request):  # S4
    return render(request, "settings/settings_activity_goal_edit.html", _base_ctx(active_tab=""))


def settings_password(request):  # S5
    return render(request, "settings/settings_password.html", _base_ctx(active_tab=""))
