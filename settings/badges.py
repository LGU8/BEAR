# settings/badges.py
# SSOT: badge_id -> static image / metadata

BADGE_MASTER = {
    # Default Profile
    "DEFAULT": {
        "image": "badges_img/profile_bear.png",
        "name": "기본 프로필",
        "desc": "기본 곰 프로필",
        "category": "profile",
    },

    # Goal badges
    "GOAL_BULKUP": {
        "image": "badges_img/bear_bulkup.png",
        "name": "벌크업 목표",
        "desc": "근성장을 목표로 하는 BEAR",
        "category": "goal",
    },
    "GOAL_DIET": {
        "image": "badges_img/bear_diet.png",
        "name": "다이어트 목표",
        "desc": "감량을 목표로 하는 BEAR",
        "category": "goal",
    },
    "GOAL_MAINTAIN": {
        "image": "badges_img/bear_maintain.png",
        "name": "유지 목표",
        "desc": "현재 상태를 유지하는 BEAR",
        "category": "goal",
    },

    # Activity badges
    "ACT_LOW": {
        "image": "badges_img/bear_낮음.png",
        "name": "활동량 낮음",
        "desc": "가벼운 활동 위주",
        "category": "activity",
    },
    "ACT_MID": {
        "image": "badges_img/bear_중간.png",
        "name": "활동량 중간",
        "desc": "일상 활동 + 가벼운 운동",
        "category": "activity",
    },
    "ACT_HIGH": {
        "image": "badges_img/bear_높음.png",
        "name": "활동량 높음",
        "desc": "주 5회 이상 운동",
        "category": "activity",
    },
    "ACT_VERY_HIGH": {
        "image": "badges_img/bear_매우 높음.png",
        "name": "활동량 매우 높음",
        "desc": "매일 운동/고강도",
        "category": "activity",
    },
}

# Settings UI icons (NOT badges)
SETTINGS_ICON = {
    "NUTRIENT_BEEF": "settings_img/icon_beef.png",
    "NUTRIENT_RICE": "settings_img/icon_rice.png",
    "NUTRIENT_SHRIMP": "settings_img/icon_shrimp.png",
    "ACCOUNT": "settings_img/icon_account.png",
    "PASSWORD": "settings_img/icon_password.png",
}
