# settings/views.py
from __future__ import annotations

from datetime import date
from typing import Optional, Dict, Any, List

from settings.badges import BADGE_MASTER
from django.contrib import messages
from django.urls import reverse
from django.shortcuts import render, redirect

# ------------------------------------------------------------
# 공통: local 더미 데이터 (나중에 DB에서 그대로 교체)
#  - DB 테이블: CUST_TM, CUS_PROFILE_TS 컬럼명 기준
# ------------------------------------------------------------
def _dummy_user() -> Dict[str, Any]:
    return {
        # CUST_TM 유사
        "cust_id": "1000000001",
        "email": "BEAR@naver.com",
        "created_dt": "20260110",  # YYYYMMDD

        # 화면용
        "nickname": "탱이",
    }


def _dummy_profile() -> Dict[str, Any]:
    return {
        # CUS_PROFILE_TS 유사
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


def _format_yyyymmdd_to_dots(s: Optional[str]) -> str:
    if not s or len(s) != 8:
        return ""
    return f"{s[0:4]}.{s[4:6]}.{s[6:8]}"


def _gender_label(gender: Optional[str]) -> str:
    if gender == "M":
        return "남"
    if gender == "F":
        return "여"
    return ""


def _calc_age_from_birth(birth_dt: Optional[str]) -> Optional[int]:
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

    # 생일 아직 안 지났으면 -1
    if (today.month, today.day) < (bm, bd):
        age -= 1

    # 비정상 값 방어 (원하면 제거 가능)
    if age < 0 or age > 130:
        return None

    return age


def _activity_copy(level: Optional[str]) -> Dict[str, str]:
    """
    S1에서 즉시 보여줄 문구 매핑
    """
    mapping = {
        "1": {"label": "낮음", "desc": "하루 종일 주로 앉아서 생활해요\n주 1~3회 가벼운 운동"},
        "2": {"label": "중간", "desc": "일상 활동이 평균이에요\n주 3회 이상 운동 중이에요"},
        "3": {"label": "높음", "desc": "활동량이 많은 편이에요\n주 5회 이상 운동"},
        "4": {"label": "매우 높음", "desc": "하루종일 활동(육체노동 등)\n매일 운동"},
    }
    return mapping.get(str(level or ""), {"label": "-", "desc": ""})


def _purpose_label(purpose: Optional[str]) -> str:
    return {"1": "다이어트", "2": "유지", "3": "벌크업"}.get(str(purpose or ""), "-")


def _segments_10(value_0_10: int) -> List[bool]:
    """
    0~10 -> 길이 10의 on/off
    (예: 3이면 True 3개, False 7개)
    """
    try:
        v = int(value_0_10)
    except Exception:
        v = 0
    v = max(0, min(10, v))
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
        # nav active
        "active_tab": active_tab,

        # badge img
        "profile_badge_img": profile_badge_img,

        # user/profile (S0~S5에서 공통 사용)
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

        # segmented(10칸) - (선택) 템플릿에서 바로 사용 가능
        "carb_segments": _segments_10(ratio_carb),
        "protein_segments": _segments_10(ratio_protein),
        "fat_segments": _segments_10(ratio_fat),

        # S1 템플릿에서 10칸 루프용(추천)
        "seg_range": range(1, 11),

        # activity/goal
        "activity_level": activity_level,
        "activity_level_label": activity_copy["label"],
        "activity_level_desc": activity_copy["desc"],

        "purpose": purpose,
        "purpose_label": purpose_label,
    }

def settings_preferences_edit(request):  # S3
    ctx = _base_ctx(active_tab="settings")

    if request.method == "POST":
        # 1) 값 파싱
        def _to_int(x, default=0):
            try:
                return int(x)
            except Exception:
                return default

        carb = _to_int(request.POST.get("ratio_carb"), 0)
        protein = _to_int(request.POST.get("ratio_protein"), 0)
        fat = _to_int(request.POST.get("ratio_fat"), 0)

        # 2) 서버 검증(필수)
        carb = max(0, min(10, carb))
        protein = max(0, min(10, protein))
        fat = max(0, min(10, fat))

        if carb + protein + fat != 10:
            # 실패: 화면 다시 렌더(입력값 유지)
            ctx["ratio_carb"] = carb
            ctx["ratio_protein"] = protein
            ctx["ratio_fat"] = fat
            ctx["ratio_sum"] = carb + protein + fat
            return render(request, "settings/settings_preferences_edit.html", ctx)

        # 3) TODO: DB UPDATE 위치
        # - CUS_PROFILE_TS: Ratio_carb=carb, Ratio_protein=protein, Ratio_fat=fat, updated_time=...
        # - cust_id는 ctx["cust_id"] 기반

        # 4) 성공 시 S1로 이동
        return redirect("settings_app:settings_account")

def settings_activity_goal_edit(request):  # S4
    ctx = _base_ctx(active_tab="settings")

    # session 값이 있으면 ctx에 덮어쓰기 (로컬 저장 반영)
    if request.session.get("activity_level"):
        ctx["activity_level"] = str(request.session["activity_level"])
        ctx["activity_level_label"] = _activity_copy(ctx["activity_level"])["label"]
        ctx["activity_level_desc"] = _activity_copy(ctx["activity_level"])["desc"]

    if request.session.get("purpose"):
        ctx["purpose"] = str(request.session["purpose"])
        ctx["purpose_label"] = _purpose_label(ctx["purpose"])

    if request.method == "POST":
        activity_level = (request.POST.get("activity_level") or "").strip()
        purpose = (request.POST.get("purpose") or "").strip()

        # 서버 검증(최소)
        if activity_level in {"1", "2", "3", "4"} and purpose in {"1", "2", "3"}:
            request.session["activity_level"] = activity_level
            request.session["purpose"] = purpose

            # 저장 후 S1로 이동
            return redirect("settings_app:settings_account")

        # 검증 실패 시: ctx 재구성(입력 반영)
        ctx["activity_level"] = activity_level
        ctx["purpose"] = purpose

# ----------------------------
# Views (S0~S5)
# ----------------------------
def settings_index(request):  # S0
    return render(request, "settings/settings_index.html", _base_ctx(active_tab="settings"))


def settings_account(request):  # S1
    return render(request, "settings/settings_account.html", _base_ctx(active_tab="settings"))


def settings_profile_edit(request):  # S2
    return render(request, "settings/settings_profile_edit.html", _base_ctx(active_tab="settings"))


def settings_preferences_edit(request):  # S3
    return render(request, "settings/settings_preferences_edit.html", _base_ctx(active_tab="settings"))


def settings_activity_goal_edit(request):  # S4
    return render(request, "settings/settings_activity_goal_edit.html", _base_ctx(active_tab="settings"))


def settings_password(request):  # S5
    ctx = _base_ctx(active_tab="settings")

    if request.method == "POST":
        cur_pw = (request.POST.get("current_password") or "").strip()
        new_pw = (request.POST.get("new_password") or "").strip()
        new_pw2 = (request.POST.get("new_password_confirm") or "").strip()

        # 최소 검증(서버에서도 동일 정책 유지)
        if not cur_pw or not new_pw or not new_pw2:
            ctx["pw_error"] = "모든 항목을 입력해주세요."
            return render(request, "settings/settings_password.html", ctx)

        if len(new_pw) < 8:
            ctx["pw_error"] = "새 비밀번호는 8자 이상이어야 해요."
            return render(request, "settings/settings_password.html", ctx)

        if new_pw != new_pw2:
            ctx["pw_error"] = "새 비밀번호와 확인이 일치하지 않아요."
            return render(request, "settings/settings_password.html", ctx)

        # TODO(DB 연동): 현재 비밀번호 검증 + 해시 저장
        # 성공 시 S1로
        return redirect(reverse("settings_app:settings_account"))
    return render(request, "settings/settings_password.html", _base_ctx(active_tab="settings"))