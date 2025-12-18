# settings/views.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Dict, Any, List

from django.db import connection
from django.shortcuts import render, redirect

from settings.badges import BADGE_MASTER
import hashlib


# ============================================================
# 0) Time helpers (DB updated_dt/updated_time 갱신용)
# ============================================================
def _now_yyyymmdd() -> str:
    return datetime.now().strftime("%Y%m%d")


def _now_yyyymmddhhmmss() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


# ============================================================
# 1) Display helpers (S0~S5 공용)
# ============================================================
def _format_yyyymmdd_to_dots(s: Optional[str]) -> str:
    if not s or len(s) != 8:
        return ""
    return f"{s[0:4]}.{s[4:6]}.{s[6:8]}"


def _gender_label(gender: Optional[str]) -> str:
    if gender == "M":
        return "남"
    if gender == "F":
        return "여"
    return "-"


def _calc_age_from_birth(birth_dt: Optional[str]) -> Optional[int]:
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

    if age < 0 or age > 130:
        return None
    return age


def _activity_copy(level: Optional[str]) -> Dict[str, str]:
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
    try:
        v = int(value_0_10)
    except Exception:
        v = 0
    v = max(0, min(10, v))
    return [i < v for i in range(10)]


# ============================================================
# 2) cust_id 결정 (요구사항)
# - request.user 우선 + session fallback
# - accounts 미완성이면 default 0000000001
# ============================================================
def _get_cust_id(request) -> str:
    u = getattr(request, "user", None)
    if u and getattr(u, "cust_id", None):
        return str(u.cust_id)

    sid = request.session.get("cust_id")
    if sid:
        return str(sid)

    return "0000000001"


# ============================================================
# 3) DB helpers (Raw SQL)
# ============================================================
def _fetch_one(sql: str, params: tuple) -> Dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
        if not row:
            return {}
        cols = [c[0] for c in cursor.description]
        return dict(zip(cols, row))


def _execute(sql: str, params: tuple) -> None:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)


# ============================================================
# 4) Base context (S0~S5 공용)
# - nickname은 CUST_TM만 사용
# - CUS_PROFILE_TS.nickname은 절대 건드리지 않음(삭제 후보)
# ============================================================
def _base_ctx(request, active_tab: str = "settings") -> Dict[str, Any]:
    cust_id = _get_cust_id(request)

    # 1) CUST_TM
    cust = _fetch_one(
        """
        SELECT cust_id, email, created_dt, nickname
        FROM CUST_TM
        WHERE cust_id = %s
        """,
        (cust_id,),
    )

    # 2) CUS_PROFILE_TS
    prof = _fetch_one(
        """
        SELECT
          cust_id,
          height_cm, weight_kg, gender, birth_dt,
          ratio_carb, ratio_protein, ratio_fat,
          activity_level, purpose
        FROM CUS_PROFILE_TS
        WHERE cust_id = %s
        """,
        (cust_id,),
    )

    # badge (현재는 DEFAULT 고정: 내일 badge 화면에서 갱신 예정)
    profile_badge_id = "DEFAULT"
    profile_badge_img = BADGE_MASTER.get(profile_badge_id, BADGE_MASTER["DEFAULT"])["image"]

    # nickname 처리 (빈 값이면 템플릿에서 안내문구 출력)
    nickname = (cust.get("nickname") or "").strip()
    nickname_is_empty = (nickname == "")
    nickname_display = nickname if nickname else "BEAR"

    created_dt_label = _format_yyyymmdd_to_dots(cust.get("created_dt"))
    gender_label = _gender_label(prof.get("gender"))
    age = _calc_age_from_birth(prof.get("birth_dt"))

    ratio_carb = int(prof.get("ratio_carb") or 0)
    ratio_protein = int(prof.get("ratio_protein") or 0)
    ratio_fat = int(prof.get("ratio_fat") or 0)
    ratio_sum = ratio_carb + ratio_protein + ratio_fat

    activity_level = str(prof.get("activity_level") or "")
    ac = _activity_copy(activity_level)

    purpose = str(prof.get("purpose") or "")
    pl = _purpose_label(purpose)

    return {
        "active_tab": active_tab,
        "profile_badge_img": profile_badge_img,

        "cust_id": cust.get("cust_id") or cust_id,
        "email": cust.get("email") or "",
        "created_dt": cust.get("created_dt") or "",
        "created_dt_label": created_dt_label,

        "nickname": nickname,
        "nickname_is_empty": nickname_is_empty,
        "nickname_display": nickname_display,

        "height_cm": prof.get("height_cm"),
        "weight_kg": prof.get("weight_kg"),
        "gender": prof.get("gender"),
        "gender_label": gender_label,
        "birth_dt": prof.get("birth_dt"),
        "age": age,

        "ratio_carb": ratio_carb,
        "ratio_protein": ratio_protein,
        "ratio_fat": ratio_fat,
        "ratio_sum": ratio_sum,

        "carb_segments": _segments_10(ratio_carb),
        "protein_segments": _segments_10(ratio_protein),
        "fat_segments": _segments_10(ratio_fat),
        "seg_range": range(1, 11),

        "activity_level": activity_level,
        "activity_level_label": ac["label"],
        "activity_level_desc": ac["desc"],

        "purpose": purpose,
        "purpose_label": pl,
    }


# ============================================================
# 5) Views (S0~S5)
# - redirect는 모두 S0(settings_index)로 통일
# ============================================================
def settings_index(request):  # S0
    ctx = _base_ctx(request, active_tab="settings")
    return render(request, "settings/settings_index.html", ctx)


def settings_account(request):  # S1
    ctx = _base_ctx(request, active_tab="settings")
    return render(request, "settings/settings_account.html", ctx)


def settings_profile_edit(request):  # S2
    ctx = _base_ctx(request, active_tab="settings")
    cust_id = ctx["cust_id"]

    if request.method == "POST":
        nickname = (request.POST.get("nickname") or "").strip()
        gender = (request.POST.get("gender") or "").strip()         # "M"/"F"
        birth_dt = (request.POST.get("birth_dt") or "").strip()     # "YYYYMMDD"
        height_cm = (request.POST.get("height_cm") or "").strip()
        weight_kg = (request.POST.get("weight_kg") or "").strip()

        if gender and gender not in {"M", "F"}:
            ctx["error"] = "성별 값 오류"
            return render(request, "settings/settings_profile_edit.html", ctx)

        if birth_dt and len(birth_dt) != 8:
            ctx["error"] = "생년월일 형식 오류(YYYYMMDD)"
            return render(request, "settings/settings_profile_edit.html", ctx)

        upd_dt = _now_yyyymmdd()
        upd_time = _now_yyyymmddhhmmss()

        # nickname -> CUST_TM only
        _execute(
            """
            UPDATE CUST_TM
            SET nickname=%s, updated_dt=%s, updated_time=%s
            WHERE cust_id=%s
            """,
            (nickname or None, upd_dt, upd_time, cust_id),
        )

        # profile -> CUS_PROFILE_TS (nickname 컬럼은 절대 건드리지 않음)
        _execute(
            """
            UPDATE CUS_PROFILE_TS
            SET gender=%s, birth_dt=%s, height_cm=%s, weight_kg=%s,
                updated_time=%s
            WHERE cust_id=%s
            """,
            (gender or None, birth_dt or None, height_cm or None, weight_kg or None, upd_time, cust_id),
        )

        return redirect("settings_app:settings_index")

    return render(request, "settings/settings_profile_edit.html", ctx)


def settings_preferences_edit(request):  # S3
    ctx = _base_ctx(request, active_tab="settings")
    cust_id = ctx["cust_id"]

    if request.method == "POST":
        def _to_int(x, default=0):
            try:
                return int(x)
            except Exception:
                return default

        carb = max(0, min(10, _to_int(request.POST.get("ratio_carb"), 0)))
        protein = max(0, min(10, _to_int(request.POST.get("ratio_protein"), 0)))
        fat = max(0, min(10, _to_int(request.POST.get("ratio_fat"), 0)))

        if carb + protein + fat != 10:
            ctx["ratio_carb"] = carb
            ctx["ratio_protein"] = protein
            ctx["ratio_fat"] = fat
            ctx["ratio_sum"] = carb + protein + fat
            ctx["error"] = "탄/단/지 합이 10이 되어야 합니다."
            return render(request, "settings/settings_preferences_edit.html", ctx)

        upd_time = _now_yyyymmddhhmmss()
        _execute(
            """
            UPDATE CUS_PROFILE_TS
            SET ratio_carb=%s, ratio_protein=%s, ratio_fat=%s,
                updated_time=%s
            WHERE cust_id=%s
            """,
            (carb, protein, fat, upd_time, cust_id),
        )
        return redirect("settings_app:settings_index")

    return render(request, "settings/settings_preferences_edit.html", ctx)


def settings_activity_goal_edit(request):  # S4
    ctx = _base_ctx(request, active_tab="settings")
    cust_id = ctx["cust_id"]

    if request.method == "POST":
        activity_level = (request.POST.get("activity_level") or "").strip()
        purpose = (request.POST.get("purpose") or "").strip()

        if activity_level not in {"1", "2", "3", "4"} or purpose not in {"1", "2", "3"}:
            ctx["error"] = "선택 값이 올바르지 않습니다."
            ctx["activity_level"] = activity_level
            ctx["purpose"] = purpose
            return render(request, "settings/settings_activity_goal_edit.html", ctx)

        upd_time = _now_yyyymmddhhmmss()
        _execute(
            """
            UPDATE CUS_PROFILE_TS
            SET activity_level=%s, purpose=%s, updated_time=%s
            WHERE cust_id=%s
            """,
            (activity_level, purpose, upd_time, cust_id),
        )
        return redirect("settings_app:settings_index")

    return render(request, "settings/settings_activity_goal_edit.html", ctx)


def settings_password(request):  # S5
    ctx = _base_ctx(request, active_tab="settings")
    cust_id = ctx["cust_id"]

    if request.method == "POST":
        cur_pw = (request.POST.get("current_password") or "").strip()
        new_pw = (request.POST.get("new_password") or "").strip()
        new_pw2 = (request.POST.get("new_password_confirm") or "").strip()

        # 1) required
        if not cur_pw or not new_pw or not new_pw2:
            ctx["error"] = "모든 항목을 입력해주세요."
            return render(request, "settings/settings_password.html", ctx)

        # 2) 길이(프론트는 8자 기준이므로 서버도 동일 권장)
        if len(new_pw) < 8:
            ctx["error"] = "새 비밀번호는 8자 이상으로 입력해주세요."
            return render(request, "settings/settings_password.html", ctx)

        # 3) 확인 일치
        if new_pw != new_pw2:
            ctx["error"] = "새 비밀번호와 확인이 일치하지 않습니다."
            return render(request, "settings/settings_password.html", ctx)

        # 4) 현재 비밀번호와 동일 방지
        if cur_pw == new_pw:
            ctx["error"] = "새 비밀번호는 현재 비밀번호와 다르게 입력해주세요."
            return render(request, "settings/settings_password.html", ctx)

        # 5) 현재 상태 조회(password/retry/lock)
        cust_auth = _fetch_one(
            """
            SELECT password, retry_cnt, lock_yn
            FROM CUST_TM
            WHERE cust_id = %s
            """,
            (cust_id,),
        )

        if not cust_auth:
            ctx["error"] = "사용자 정보를 찾을 수 없습니다."
            return render(request, "settings/settings_password.html", ctx)

        lock_yn = (cust_auth.get("lock_yn") or "N").strip()
        retry_cnt = int(cust_auth.get("retry_cnt") or 0)
        db_hash = (cust_auth.get("password") or "").strip()

        # 6) 잠금이면 차단
        if lock_yn == "Y":
            ctx["error"] = "계정이 잠겨 있어요. 관리자에게 문의해주세요."
            return render(request, "settings/settings_password.html", ctx)

        # 7) 현재 비밀번호 검증(SHA256)
        cur_hash = hashlib.sha256(cur_pw.encode("utf-8")).hexdigest()
        if cur_hash != db_hash:
            retry_cnt += 1
            new_lock = "Y" if retry_cnt >= 5 else "N"
            upd_dt = _now_yyyymmdd()
            upd_time = _now_yyyymmddhhmmss()

            _execute(
                """
                UPDATE CUST_TM
                SET retry_cnt=%s, lock_yn=%s, updated_dt=%s, updated_time=%s
                WHERE cust_id=%s
                """,
                (retry_cnt, new_lock, upd_dt, upd_time, cust_id),
            )

            ctx["error"] = "현재 비밀번호가 올바르지 않습니다."
            return render(request, "settings/settings_password.html", ctx)

        # 8) 변경 저장
        new_hash = hashlib.sha256(new_pw.encode("utf-8")).hexdigest()
        upd_dt = _now_yyyymmdd()
        upd_time = _now_yyyymmddhhmmss()

        _execute(
            """
            UPDATE CUST_TM
            SET password=%s, retry_cnt=%s, lock_yn=%s, updated_dt=%s, updated_time=%s
            WHERE cust_id=%s
            """,
            (new_hash, 0, "N", upd_dt, upd_time, cust_id),
        )

        return redirect("settings_app:settings_index")

    return render(request, "settings/settings_password.html", ctx)
