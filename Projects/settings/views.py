# settings/views.py
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Dict, Any, List

import json
import os
import re

from django.contrib.auth.decorators import login_required
from django.db import connection, transaction
from django.shortcuts import render, redirect
from django.utils import timezone

from accounts.models import CusBadge
from settings.utils.security import verify_password, hash_password

DEFAULT_PROFILE_BADGE = "icons_img/bear_welcome.png"

# ============================================================
# ✅ [필수] CUS_PROFILE_TS 실제 컬럼명 (스크린샷 기준)
# ============================================================
RECO_KCAL_COL = "Recommended_calories"
BURNED_KCAL_COL = "Calories_burned"
OFFSET_COL = "Offset"

RATIO_CARB_COL = "Ratio_carb"
RATIO_PROTEIN_COL = "Ratio_protein"
RATIO_FAT_COL = "Ratio_fat"


# ============================================================
# 0) Time helpers (DB updated_dt/updated_time 갱신용)
# - ✅ KST(Asia/Seoul) 적용: timezone.localtime(timezone.now())
# ============================================================
def _now_yyyymmdd() -> str:
    return timezone.localtime(timezone.now()).strftime("%Y%m%d")


def _now_yyyymmddhhmmss() -> str:
    return timezone.localtime(timezone.now()).strftime("%Y%m%d%H%M%S")


# ============================================================
# ✅ 0-1) Calories helpers (Signup과 동일하게 계산하기 위한 유틸)
# ============================================================
def _activity_factor(level: str) -> float:
    return {
        "1": 1.2,
        "2": 1.375,
        "3": 1.55,
        "4": 1.725,
    }.get(str(level or ""), 1.2)


def _purpose_offset_kcal(purpose: str) -> int:
    return {
        "1": -400,
        "2": 0,
        "3": 400,
    }.get(str(purpose or ""), 0)


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _to_int(x: Any, default: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def _calc_bmr_msj(height_cm: Any, weight_kg: Any, age: Any, gender: Any) -> int:
    """
    Mifflin-St Jeor
    남: 10w + 6.25h - 5a + 5
    여: 10w + 6.25h - 5a - 161
    """
    h = _to_float(height_cm, 0.0)
    w = _to_float(weight_kg, 0.0)
    a = _to_int(age, 0)

    if h <= 0 or w <= 0 or a <= 0:
        return 0

    g = str(gender or "").strip().upper()
    if g == "F":
        bmr = (10 * w) + (6.25 * h) - (5 * a) - 161
    else:
        bmr = (10 * w) + (6.25 * h) - (5 * a) + 5

    return int(round(bmr))


def _calc_tdee(height_cm: Any, weight_kg: Any, age: Any, gender: Any, activity_level: str) -> int:
    bmr = _calc_bmr_msj(height_cm, weight_kg, age, gender)
    if bmr <= 0:
        return 0
    return int(round(bmr * _activity_factor(activity_level)))


def _calc_target_kcal(height_cm: Any, weight_kg: Any, age: Any, gender: Any, activity_level: str, purpose: str) -> int:
    tdee = _calc_tdee(height_cm, weight_kg, age, gender, activity_level)
    if tdee <= 0:
        return 0

    target = tdee + _purpose_offset_kcal(purpose)

    if target < 1200:
        target = 1200

    return int(target)


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
# 2) cust_id 결정
# - request.user 우선 + session fallback
# ============================================================
def _get_cust_id(request) -> str:
    u = getattr(request, "user", None)
    if u and getattr(u, "cust_id", None):
        return str(u.cust_id)

    sid = request.session.get("cust_id")
    if sid:
        return str(sid)

    return ""


def _require_cust_id_or_redirect(request):
    cust_id = _get_cust_id(request)
    if not cust_id:
        return None, redirect("accounts_app:user_login")
    return cust_id, None


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

    cust = _fetch_one(
        """
        SELECT cust_id, email, created_dt, nickname
        FROM CUST_TM
        WHERE cust_id = %s
        """,
        (cust_id,),
    )

    # ✅ 스크린샷 실제 컬럼명 → alias로 기존 key 유지
    prof = _fetch_one(
        f"""
        SELECT
          cust_id,
          height_cm, weight_kg, gender, birth_dt,
          {RATIO_CARB_COL}   AS ratio_carb,
          {RATIO_PROTEIN_COL} AS ratio_protein,
          {RATIO_FAT_COL}    AS ratio_fat,
          activity_level, purpose,
          selected_badge_id
        FROM CUS_PROFILE_TS
        WHERE cust_id = %s
        """,
        (cust_id,),
    )

    selected_badge_id = (prof.get("selected_badge_id") or "").strip()
    profile_badge_img = f"badges_img/{selected_badge_id}.png" if selected_badge_id else DEFAULT_PROFILE_BADGE

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
        "selected_badge_id": selected_badge_id,

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
# 4-1) Badge meta safe loader (JSONDecodeError 방지)
# ============================================================
def _load_badge_meta() -> Dict[str, Any]:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    meta_path = os.path.join(base_dir, "badges_meta", "badge_meta.json")

    default = {
        "img_base": "/static/badges_img",
        "items": [],
        "_meta_path": meta_path,
        "_meta_error": "",
    }

    if not os.path.exists(meta_path):
        default["_meta_error"] = f"badge_meta.json not found: {meta_path}"
        return default

    try:
        with open(meta_path, "r", encoding="utf-8-sig") as f:
            raw = f.read()

        if not raw or not raw.strip():
            default["_meta_error"] = f"badge_meta.json is empty: {meta_path}"
            return default

        data = json.loads(raw)

        if not isinstance(data, dict):
            default["_meta_error"] = "badge_meta.json root must be object"
            return default

        if "items" not in data or not isinstance(data.get("items"), list):
            data["items"] = []

        if "img_base" not in data or not isinstance(data.get("img_base"), str):
            data["img_base"] = "/static/badges_img"

        data["_meta_path"] = meta_path
        data["_meta_error"] = ""
        return data

    except json.JSONDecodeError as e:
        default["_meta_error"] = f"JSONDecodeError: {str(e)}"
        return default
    except Exception as e:
        default["_meta_error"] = f"meta load error: {str(e)}"
        return default


# ============================================================
# 4-2) Badge rule evaluator (Model 매핑 없이 Raw SQL로 판정)
# ============================================================
_SAFE_IDENT = re.compile(r"^[A-Z0-9_]+$")


def _safe_ident(name: str) -> bool:
    return bool(name and _SAFE_IDENT.match(name))


def _count_rows(table: str, cust_id: str, filters: Dict[str, Any]) -> int:
    if not _safe_ident(table):
        return 0

    where = ["cust_id = %s"]
    params: List[Any] = [cust_id]

    for k, v in (filters or {}).items():
        if not _safe_ident(str(k).upper()):
            continue
        where.append(f"{k} = %s")
        params.append(v)

    sql = f"SELECT COUNT(*) AS cnt FROM {table} WHERE " + " AND ".join(where)

    with connection.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        row = cursor.fetchone()
        return int(row[0] or 0) if row else 0


def _eval_badge_unlock(cust_id: str, badge_item: Dict[str, Any]) -> bool:
    unlock_type = (badge_item.get("unlock_type") or "").strip()
    rule = badge_item.get("unlock_rule") or {}

    if unlock_type != "count":
        return False

    table = (rule.get("table") or "").strip()
    metric = (rule.get("metric") or "rows").strip()
    filters = rule.get("filters") or {}
    need = int(rule.get("count") or 0)

    if need <= 0:
        return False

    if metric == "rows":
        value = _count_rows(table, cust_id, filters)
        return value >= need

    return False


def _sync_acquired_badges(cust_id: str, items: List[Dict[str, Any]]) -> None:
    if not cust_id:
        return

    existing = set(
        CusBadge.objects.filter(cust_id=cust_id).values_list("badge_id", flat=True)
    )

    to_create = []
    now = timezone.now()

    for it in items:
        badge_id = str(it.get("badge_id") or "").strip()
        if not badge_id:
            continue
        if badge_id in existing:
            continue

        if _eval_badge_unlock(cust_id, it):
            to_create.append(
                CusBadge(
                    cust_id=cust_id,
                    badge_id=badge_id,
                    acquired_time=now,
                )
            )

    if to_create:
        with transaction.atomic():
            CusBadge.objects.bulk_create(to_create, ignore_conflicts=True)


# ============================================================
# 5) Views (S0~S5)
# ============================================================
@login_required(login_url="accounts_app:user_login")
def settings_index(request):  # S0
    cust_id, resp = _require_cust_id_or_redirect(request)
    if resp:
        return resp
    ctx = _base_ctx(request, active_tab="settings")
    return render(request, "settings/settings_index.html", ctx)


@login_required(login_url="accounts_app:user_login")
def settings_account(request):  # S1
    cust_id, resp = _require_cust_id_or_redirect(request)
    if resp:
        return resp
    ctx = _base_ctx(request, active_tab="settings")
    return render(request, "settings/settings_account.html", ctx)


@login_required(login_url="accounts_app:user_login")
def settings_profile_edit(request):  # S2
    cust_id, resp = _require_cust_id_or_redirect(request)
    if resp:
        return resp

    ctx = _base_ctx(request, active_tab="settings")

    meta = _load_badge_meta()
    items = meta.get("items", [])
    img_base = meta.get("img_base", "/static/badges_img")

    acquired_rows = (
        CusBadge.objects
        .filter(cust_id=cust_id)
        .values("badge_id", "acquired_time")
    )
    acquired_set = {r["badge_id"] for r in acquired_rows}

    def normalize_for_picker(x):
        badge_id = str(x.get("badge_id", "")).strip()
        is_acquired = badge_id in acquired_set
        return {
            "badge_id": badge_id,
            "category": x.get("category"),
            "sort_no": int(x.get("sort_no", 999999)),
            "img_url": f"{img_base}/{badge_id}.png",
            "title": x.get("title", ""),
            "desc": x.get("desc", ""),
            "hint": x.get("hint", ""),
            "locked": (not is_acquired),
        }

    picker_items = sorted(
        [normalize_for_picker(x) for x in items if x.get("badge_id")],
        key=lambda r: r["sort_no"]
    )

    ctx.update({
        "picker_items": picker_items,
        "selected_badge_id": ctx.get("selected_badge_id", ""),
        "badge_meta_error": meta.get("_meta_error", ""),
        "badge_meta_path": meta.get("_meta_path", ""),
    })

    if request.method == "POST":
        nickname = (request.POST.get("nickname") or "").strip()
        gender = (request.POST.get("gender") or "").strip()
        birth_dt = (request.POST.get("birth_dt") or "").strip()
        height_cm = (request.POST.get("height_cm") or "").strip()
        weight_kg = (request.POST.get("weight_kg") or "").strip()
        selected_badge_id = (request.POST.get("selected_badge_id") or "").strip()

        if gender and gender not in {"M", "F"}:
            ctx["error"] = "성별 값 오류"
            return render(request, "settings/settings_profile_edit.html", ctx)

        if birth_dt and len(birth_dt) != 8:
            ctx["error"] = "생년월일 형식 오류(YYYYMMDD)"
            return render(request, "settings/settings_profile_edit.html", ctx)

        if selected_badge_id:
            has_badge = CusBadge.objects.filter(
                cust_id=cust_id,
                badge_id=selected_badge_id
            ).exists()
            if not has_badge:
                ctx["error"] = "아직 획득하지 않은 배지는 선택할 수 없어요."
                return render(request, "settings/settings_profile_edit.html", ctx)

        upd_dt = _now_yyyymmdd()
        upd_time = _now_yyyymmddhhmmss()

        _execute(
            """
            UPDATE CUST_TM
            SET nickname=%s, updated_dt=%s, updated_time=%s
            WHERE cust_id=%s
            """,
            (nickname or None, upd_dt, upd_time, cust_id),
        )

        _execute(
            """
            UPDATE CUS_PROFILE_TS
            SET gender=%s, birth_dt=%s, height_cm=%s, weight_kg=%s,
                selected_badge_id=%s,
                updated_time=%s
            WHERE cust_id=%s
            """,
            (
                gender or None,
                birth_dt or None,
                height_cm or None,
                weight_kg or None,
                selected_badge_id or None,
                upd_time,
                cust_id,
            ),
        )

        return redirect("settings_app:settings_index")

    return render(request, "settings/settings_profile_edit.html", ctx)


@login_required(login_url="accounts_app:user_login")
def settings_preferences_edit(request):  # S3
    cust_id, resp = _require_cust_id_or_redirect(request)
    if resp:
        return resp

    ctx = _base_ctx(request, active_tab="settings")

    if request.method == "POST":
        def _to_int_local(x, default=0):
            try:
                return int(x)
            except Exception:
                return default

        carb = max(0, min(10, _to_int_local(request.POST.get("ratio_carb"), 0)))
        protein = max(0, min(10, _to_int_local(request.POST.get("ratio_protein"), 0)))
        fat = max(0, min(10, _to_int_local(request.POST.get("ratio_fat"), 0)))

        if carb + protein + fat != 10:
            ctx["ratio_carb"] = carb
            ctx["ratio_protein"] = protein
            ctx["ratio_fat"] = fat
            ctx["ratio_sum"] = carb + protein + fat
            ctx["error"] = "탄/단/지 합이 10이 되어야 합니다."
            return render(request, "settings/settings_preferences_edit.html", ctx)

        upd_time = _now_yyyymmddhhmmss()

        # ✅ 실제 컬럼명 Ratio_* 로 UPDATE
        _execute(
            f"""
            UPDATE CUS_PROFILE_TS
            SET {RATIO_CARB_COL}=%s, {RATIO_PROTEIN_COL}=%s, {RATIO_FAT_COL}=%s,
                updated_time=%s
            WHERE cust_id=%s
            """,
            (carb, protein, fat, upd_time, cust_id),
        )
        return redirect("settings_app:settings_index")

    return render(request, "settings/settings_preferences_edit.html", ctx)

# settings/views.py (S4 only - FINAL)

@login_required(login_url="accounts_app:user_login")
def settings_activity_goal_edit(request):  # S4 ✅ FINAL
    cust_id, resp = _require_cust_id_or_redirect(request)
    if resp:
        return resp

    ctx = _base_ctx(request, active_tab="settings")

    # 계산에 필요한 프로필(키/몸무게/성별/생년월일)
    prof_for_calc = _fetch_one(
        """
        SELECT height_cm, weight_kg, gender, birth_dt
        FROM CUS_PROFILE_TS
        WHERE cust_id=%s
        """,
        (cust_id,),
    )
    age = _calc_age_from_birth(prof_for_calc.get("birth_dt")) or 0

    cur_activity = str(ctx.get("activity_level") or "")
    cur_purpose = str(ctx.get("purpose") or "")

    # 현재(초기) Target kcal (서버 계산값)
    cur_target_kcal = _calc_target_kcal(
        prof_for_calc.get("height_cm"),
        prof_for_calc.get("weight_kg"),
        age,
        prof_for_calc.get("gender"),
        cur_activity,
        cur_purpose,
    )

    # ✅ activity별 TDEE dict (템플릿에서 json_script로 안전하게 전달)
    tdee_by_level = {}
    for lv in ["1", "2", "3", "4"]:
        tdee_by_level[lv] = _calc_tdee(
            prof_for_calc.get("height_cm"),
            prof_for_calc.get("weight_kg"),
            age,
            prof_for_calc.get("gender"),
            lv,
        )

    ctx.update({
        "cur_target_kcal": cur_target_kcal,
        "tdee_by_level": tdee_by_level,  # ✅ dict 그대로
    })

    if request.method == "POST":
        activity_level = (request.POST.get("activity_level") or "").strip()
        purpose = (request.POST.get("purpose") or "").strip()

        if activity_level not in {"1", "2", "3", "4"} or purpose not in {"1", "2", "3"}:
            ctx["error"] = "선택 값이 올바르지 않습니다."
            ctx["activity_level"] = activity_level
            ctx["purpose"] = purpose
            return render(request, "settings/settings_activity_goal_edit.html", ctx)

        # ✅ Signup과 동일 계산 세트
        burned_kcal = _calc_tdee(
            prof_for_calc.get("height_cm"),
            prof_for_calc.get("weight_kg"),
            age,
            prof_for_calc.get("gender"),
            activity_level,
        )
        offset_kcal = _purpose_offset_kcal(purpose)

        target_kcal = _calc_target_kcal(
            prof_for_calc.get("height_cm"),
            prof_for_calc.get("weight_kg"),
            age,
            prof_for_calc.get("gender"),
            activity_level,
            purpose,
        )

        upd_time = _now_yyyymmddhhmmss()

        # ✅ 실제 컬럼명으로 저장 (Recommended_calories / Calories_burned / Offset)
        _execute(
            f"""
            UPDATE CUS_PROFILE_TS
            SET activity_level=%s,
                purpose=%s,
                {BURNED_KCAL_COL}=%s,
                {RECO_KCAL_COL}=%s,
                `{OFFSET_COL}`=%s,
                updated_time=%s
            WHERE cust_id=%s
            """,
            (activity_level, purpose, burned_kcal, target_kcal, offset_kcal, upd_time, cust_id),
        )

        return redirect("settings_app:settings_index")

    return render(request, "settings/settings_activity_goal_edit.html", ctx)

@login_required(login_url="accounts_app:user_login")
def settings_password(request):  # S5
    cust_id, resp = _require_cust_id_or_redirect(request)
    if resp:
        return resp

    ctx = _base_ctx(request, active_tab="settings")

    if request.method == "POST":
        cur_pw = (request.POST.get("current_password") or "").strip()
        new_pw = (request.POST.get("new_password") or "").strip()
        new_pw2 = (request.POST.get("new_password_confirm") or "").strip()

        if not cur_pw or not new_pw or not new_pw2:
            ctx["error"] = "모든 항목을 입력해주세요."
            return render(request, "settings/settings_password.html", ctx)

        if len(new_pw) < 8:
            ctx["error"] = "새 비밀번호는 8자 이상으로 입력해주세요."
            return render(request, "settings/settings_password.html", ctx)

        if new_pw != new_pw2:
            ctx["error"] = "새 비밀번호와 확인이 일치하지 않습니다."
            return render(request, "settings/settings_password.html", ctx)

        if cur_pw == new_pw:
            ctx["error"] = "새 비밀번호는 현재 비밀번호와 다르게 입력해주세요."
            return render(request, "settings/settings_password.html", ctx)

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

        if lock_yn == "Y":
            ctx["error"] = "계정이 잠겨 있어요. 관리자에게 문의해주세요."
            return render(request, "settings/settings_password.html", ctx)

        if not verify_password(cur_pw, db_hash):
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

        new_hash = hash_password(new_pw)
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


@login_required(login_url="accounts_app:user_login")
def settings_badges(request):
    cust_id, resp = _require_cust_id_or_redirect(request)
    if resp:
        return resp

    ctx = _base_ctx(request, active_tab="collection")

    meta = _load_badge_meta()
    items = meta.get("items", [])

    _sync_acquired_badges(cust_id, items)

    img_base = (meta.get("img_base") or "/static/badges_img").strip()
    if not img_base.startswith("/"):
        img_base = "/" + img_base
    if not img_base.startswith("/static/"):
        if img_base.startswith("/badges_img"):
            img_base = "/static" + img_base

    acquired_rows = (
        CusBadge.objects
        .filter(cust_id=cust_id)
        .values_list("badge_id", "acquired_time")
    )

    acquired_map = {}
    for badge_id, acquired_time in acquired_rows:
        if acquired_time is None:
            acquired_map[str(badge_id)] = ""
        else:
            if isinstance(acquired_time, datetime):
                acquired_map[str(badge_id)] = acquired_time.strftime("%Y%m%d%H%M%S")
            else:
                s = str(acquired_time).strip()
                digits = "".join(ch for ch in s if ch.isdigit())
                acquired_map[str(badge_id)] = digits if digits else s

    acquired_set = set(acquired_map.keys())

    def normalize_item(x):
        badge_id = str(x.get("badge_id", "")).strip()
        is_acquired = badge_id in acquired_set
        acquired_time = acquired_map.get(badge_id, "") if is_acquired else ""

        return {
            "badge_id": badge_id,
            "category": x.get("category"),
            "sort_no": int(x.get("sort_no", 999999)),
            "img_url": f"{img_base}/{badge_id}.png",
            "title": x.get("title", ""),
            "desc": x.get("desc", ""),
            "hint": x.get("hint", ""),
            "locked": (not is_acquired),
            "acquired_time": acquired_time,
        }

    norm = [normalize_item(x) for x in items if x.get("badge_id")]

    def _sort_key(r):
        if not r.get("locked", True):
            at = r.get("acquired_time") or ""
            if at.isdigit():
                return (0, -int(at), r.get("sort_no", 999999))
            return (0, 0, r.get("sort_no", 999999))
        return (1, r.get("sort_no", 999999))

    food_badges = sorted([x for x in norm if x["category"] == "F"], key=_sort_key)
    emotion_badges = sorted([x for x in norm if x["category"] == "E"], key=_sort_key)

    total = len(norm)
    acquired = len(acquired_set)
    rate = int(round((acquired / total) * 100)) if total else 0
    rate = max(0, min(100, rate))

    ctx.update({
        "cust_id": cust_id,
        "food_badges": food_badges,
        "emotion_badges": emotion_badges,
        "badge_total": total,
        "badge_acquired": acquired,
        "badge_rate": rate,
        "active_tab": "collection",

        "badge_meta_error": meta.get("_meta_error", ""),
        "badge_meta_path": meta.get("_meta_path", ""),
    })
    return render(request, "settings/settings_badges.html", ctx)