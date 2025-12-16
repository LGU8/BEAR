from django.shortcuts import render
from settings.badges import BADGE_MASTER

def _base_ctx(active_tab: str = ""):
    profile_badge_id = "DEFAULT"  # TODO: DB 연동 후 cust_id 기반으로 교체
    profile_badge_img = BADGE_MASTER[profile_badge_id]["image"]

    # 더미 데이터_선호 영양소 3질문지 비율
    ratio_carb = 2
    ratio_protein = 5
    ratio_fat = 3  # 2+5+3=10

    return {
        "active_tab": active_tab,
        "profile_badge_img": profile_badge_img,
        "ratio_carb": ratio_carb,
        "ratio_protein": ratio_protein,
        "ratio_fat": ratio_fat,
    }

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
    return render(request, "settings/settings_password.html", _base_ctx(active_tab="settings"))
