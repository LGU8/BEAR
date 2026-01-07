from django.shortcuts import render, redirect
from datetime import date, datetime, timedelta
from django.utils import timezone
import json
from django.db import connection
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count

from record.models import CusFeelTh
from record.models import ReportTh
from django.urls import reverse
from django.http import HttpResponse, HttpResponseForbidden

import logging

logger = logging.getLogger("django.security.csrf")

def csrf_failure(request, reason=""):
    logger.error(
        "[CSRF_FAIL] path=%s method=%s reason=%s referer=%s origin=%s host=%s",
        request.path,
        request.method,
        reason,
        request.META.get("HTTP_REFERER"),
        request.META.get("HTTP_ORIGIN"),
        request.get_host(),
    )
    return HttpResponseForbidden("CSRF Failed")


def public_home(request):
    # ✅ DB/세션/로그인 의존 없이 렌더만 되는 템플릿
    # home.html을 그대로 쓰면 내부에서 context 기대할 수 있으니
    # public 전용 템플릿을 하나 두는 게 안전
    return render(request, "public_home.html")



import logging
logger = logging.getLogger(__name__)

# conf/views.py (상단 또는 _safe_get_cust_id 위)

def _normalize_cust_id(v) -> str:
    """
    DB의 cust_id가 10자리 zero-padding(예: 0000000025)인 전제에 맞춰 정규화.
    - int/str 모두 처리
    - 숫자면 zfill(10)
    - 그 외는 strip만
    """
    if v is None:
        return ""
    s = str(v).strip()
    if not s:
        return ""
    if s.isdigit():
        return s.zfill(10)
    return s


def _safe_get_cust_id(request) -> str:
    # 1) authenticated user의 cust_id
    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        cust_id = getattr(user, "cust_id", None)
        cust_id = _normalize_cust_id(cust_id)
        if cust_id:
            return cust_id

    # 2) session cust_id (보조)
    sess = getattr(request, "session", None)
    if sess:
        cust_id = sess.get("cust_id")
        cust_id = _normalize_cust_id(cust_id)
        if cust_id:
            return cust_id

    # 3) 없으면 로그 남기고 빈 값
    logger.warning(
        "[AUTH] cust_id not found (user_email=%s, session_keys=%s)",
        getattr(user, "email", None),
        list(getattr(request, "session", {}).keys()) if getattr(request, "session", None) else [],
    )
    return ""





def _build_daily_report_chart(cust_id: str, today_ymd: str) -> dict:
    """
    Home - 일일 리포트 섹션용 데이터 빌더.
    조건: type='D' AND rgs_dt=today_ymd AND cust_id=cust_id
    다건이면 updated_time 최신 1건.
    """
    if not cust_id:
        return {"rgs_dt": today_ymd, "content": ""}

    row = (
        ReportTh.objects.filter(cust_id=cust_id, type="D", rgs_dt=today_ymd)
        .order_by("-updated_time")
        .first()
    )

    if not row or not getattr(row, "content", None):
        return {"rgs_dt": today_ymd, "content": ""}

    return {"rgs_dt": row.rgs_dt, "content": row.content}


def _kst_now():
    try:
        return timezone.localtime()
    except Exception:
        return datetime.now()


def _is_before_4am_kst() -> bool:
    now_kst = _kst_now()
    return now_kst.hour < 4


def _exists_food_slot(cust_id: str, ymd: str, slot: str) -> bool:
    sql = """
        SELECT 1
        FROM CUS_FOOD_TH
        WHERE cust_id = %s AND rgs_dt = %s AND time_slot = %s
        LIMIT 1;
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [cust_id, ymd, slot])
        return cursor.fetchone() is not None


def _exists_feel_slot(cust_id: str, ymd: str, slot: str) -> bool:
    sql = """
        SELECT 1
        FROM CUS_FEEL_TH
        WHERE cust_id = %s AND rgs_dt = %s AND time_slot = %s
        LIMIT 1;
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [cust_id, ymd, slot])
        return cursor.fetchone() is not None


def _is_slot_done(cust_id: str, ymd: str, slot: str) -> bool:
    return _exists_food_slot(cust_id, ymd, slot) and _exists_feel_slot(
        cust_id, ymd, slot
    )


def _next_slot_by_food_and_feel(cust_id: str, ymd: str):
    """
    다음 추천 slot 결정(그 날짜 ymd 기준):
    - D done -> DONE
    - L done -> D
    - M done -> L
    - else  -> M
    """
    done_m = _is_slot_done(cust_id, ymd, "M")
    done_l = _is_slot_done(cust_id, ymd, "L")
    done_d = _is_slot_done(cust_id, ymd, "D")

    if done_d:
        return ("DONE", {"M": done_m, "L": done_l, "D": done_d})
    if done_l:
        return ("D", {"M": done_m, "L": done_l, "D": done_d})
    if done_m:
        return ("L", {"M": done_m, "L": done_l, "D": done_d})
    return ("M", {"M": done_m, "L": done_l, "D": done_d})


def _get_food_name_column() -> str:
    candidates = ["name", "food_nm", "food_name", "food_nm_kr", "title", "food_title"]

    sql = """
        SELECT COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'FOOD_TB';
    """
    with connection.cursor() as cursor:
        cursor.execute(sql)
        cols = {str(r[0]) for r in cursor.fetchall()}

    for c in candidates:
        if c in cols:
            return c
    return ""


# 완료 슬롯 찾아서 slot 사용하기
def _last_done_slot_by_food_and_feel(cust_id: str, ymd: str) -> str | None:
    slots = ["M", "L", "D"]
    done = []
    with connection.cursor() as cursor:
        for s in slots:
            cursor.execute(
                """
                SELECT 1
                FROM CUS_FOOD_TH f
                JOIN CUS_FEEL_TH e
                  ON e.cust_id=f.cust_id
                 AND e.rgs_dt=f.rgs_dt
                 AND e.seq=f.seq
                 AND e.time_slot=f.time_slot
                WHERE f.cust_id=%s AND f.rgs_dt=%s AND f.time_slot=%s
                LIMIT 1
                """,
                [cust_id, ymd, s],
            )
            if cursor.fetchone() is not None:
                done.append(s)
    return done[-1] if done else None


def _recommend_target_slot_from_trigger_slot(trigger_slot: str) -> str:
    """
    ✅ MENU_RECOM_TH.rec_time_slot(트리거 슬롯) -> 화면에 보여줄 추천 대상 슬롯
    - M(아침 기록 완료) -> L(점심 추천)
    - L(점심 기록 완료) -> D(저녁 추천)
    - D(저녁 기록 완료) -> DONE (오늘 완료 상태)
    """
    s = (trigger_slot or "").strip().upper()
    return {"M": "L", "L": "D", "D": "DONE"}.get(s, "M")

def _derive_reco_target(rgs_dt: str, recorded_slot: str):
    """
    ✅ 추천 저장/표출 공통 키 생성 로직

    recorded_slot(기록 슬롯: M/L/D) 기준:
    - M 기록 완료 -> (같은날, L 추천 저장/조회)
    - L 기록 완료 -> (같은날, D 추천 저장/조회)
    - D 기록 완료 -> (다음날, M 추천 저장/조회)

    반환: (reco_rgs_dt, reco_time_slot)
    """
    rgs_dt = (rgs_dt or "").strip()
    recorded_slot = (recorded_slot or "").strip().upper()

    # 입력 방어
    if len(rgs_dt) != 8 or not rgs_dt.isdigit():
        return "", ""

    if recorded_slot == "M":
        return rgs_dt, "L"
    if recorded_slot == "L":
        return rgs_dt, "D"
    if recorded_slot == "D":
        try:
            dt = datetime.strptime(rgs_dt, "%Y%m%d").date()
            dt2 = dt + timedelta(days=1)
            return dt2.strftime("%Y%m%d"), "M"
        except Exception:
            return "", ""

    return "", ""

def _build_menu_reco_context(cust_id: str) -> dict:
    base = {
        "is_done": False,
        "status_text": "추천 준비 중",
        "title": "",
        "line": "",
        "ymd": "",
    }
    if not cust_id:
        return base

    today_ymd = timezone.localdate().strftime("%Y%m%d")
    yesterday_ymd = (timezone.localdate() - timedelta(days=1)).strftime("%Y%m%d")
    base["ymd"] = today_ymd

    # 1) 새벽 4시 이전 + 어제 DONE이면 완료 문구 유지
    if _is_before_4am_kst():
        y_slot_or_done, _ = _next_slot_by_food_and_feel(cust_id, yesterday_ymd)
        if y_slot_or_done == "DONE":
            base["is_done"] = True
            base["status_text"] = "오늘 식사 기록이 모두 완료됐어요. 추천 준비 중"
            return base

    # 2) 오늘 DONE이면 완료 문구
    slot_or_done, _ = _next_slot_by_food_and_feel(cust_id, today_ymd)
    if slot_or_done == "DONE":
        base["is_done"] = True
        base["status_text"] = "오늘 식사 기록이 모두 완료됐어요. 추천 준비 중"
        return base

    # 3) 트리거 슬롯 결정
    #    - 우선 오늘에서 마지막 done 슬롯 찾기
    trigger_ymd = today_ymd
    reco_key_slot = _last_done_slot_by_food_and_feel(cust_id, today_ymd)

    # ✅ (핵심) 오늘 done 슬롯이 없으면:
    #    - 어제 마지막 done 슬롯이 D인지 확인해서 "오늘 아침(M) 추천"을 보여줄 수 있게 한다.
    if not reco_key_slot:
        y_last = _last_done_slot_by_food_and_feel(cust_id, yesterday_ymd)
        if y_last == "D":
            trigger_ymd = yesterday_ymd
            reco_key_slot = "D"
        else:
            base["status_text"] = "추천 준비 중"
            return base

    # 4) display_slot 계산
    #    - 어제 D 트리거면: 오늘 아침 추천이므로 display_slot은 M
    if trigger_ymd == yesterday_ymd and reco_key_slot == "D":
        display_slot = "M"
    else:
        display_slot = _recommend_target_slot_from_trigger_slot(reco_key_slot)

    if display_slot == "DONE":
        base["is_done"] = True
        base["status_text"] = "오늘 식사 기록이 모두 완료됐어요. 추천 준비 중"
        return base

    slot_label = {"M": "아침", "L": "점심", "D": "저녁"}[display_slot]
    base["title"] = f"{slot_label} 메뉴 추천"

    # 5) MENU_RECOM_TH 조회 키 계산(저장 로직과 동일)
    #    - trigger_ymd / reco_key_slot 기준으로 추천 대상 키 도출
    reco_rgs_dt, reco_time_slot = _derive_reco_target(trigger_ymd, reco_key_slot)

    reco_rgs_dt = (reco_rgs_dt or "").strip()
    reco_time_slot = (reco_time_slot or "").strip().upper()
    if not reco_rgs_dt or reco_time_slot not in ("M", "L", "D"):
        base["status_text"] = "추천 준비 중"
        return base

    # 6) 추천 로딩
    name_col = _get_food_name_column()
    if not name_col:
        base["status_text"] = "추천 준비 중"
        return base

    sql_reco = f"""
        SELECT
            r.rec_type,
            r.food_id,
            f.`{name_col}` AS food_name
        FROM MENU_RECOM_TH r
        JOIN FOOD_TB f
          ON f.food_id = r.food_id
        WHERE r.cust_id = %s
          AND r.rgs_dt = %s
          AND r.rec_time_slot = %s
          AND r.rec_type IN ('P','H','E')
        ORDER BY FIELD(r.rec_type, 'P','H','E');
    """
    with connection.cursor() as cursor:
        cursor.execute(sql_reco, [cust_id, reco_rgs_dt, reco_time_slot])
        rows = cursor.fetchall()

    if not rows:
        base["status_text"] = "추천 준비 중"
        return base

    type_label = {"P": "취향 기반", "H": "균형(5:3:2)", "E": "새로운 메뉴"}

    parts = []
    for rec_type, food_id, food_name in rows:
        t = str(rec_type).strip().upper()
        nm = str(food_name).strip() if food_name is not None else ""
        if nm:
            parts.append(f"{type_label.get(t, t)}: {nm}")

    if not parts:
        base["status_text"] = "추천 준비 중"
        return base

    # ✅ 디버그 로그(문제 해결 후 logger.debug로 낮추는 것 권장)
    print(
        "[menu_reco]",
        "cust_id=", cust_id,
        "today_ymd=", today_ymd,
        "trigger_ymd=", trigger_ymd,
        "reco_key_slot=", reco_key_slot,
        "display_slot=", display_slot,
        "reco_rgs_dt=", reco_rgs_dt,
        "reco_time_slot=", reco_time_slot,
        "rows=", rows,
    )

    base["status_text"] = ""
    base["line"] = " / ".join(parts)
    return base



def _build_today_donut(cust_id: str, yyyymmdd: str):
    """
    CUS_FEEL_TH에서 오늘(cust_id, rgs_dt)의 mood를 집계해서
    donut dict를 만들고, 데이터 없으면 None 반환.
    """
    if not cust_id:
        return None

    qs = (
        CusFeelTh.objects.filter(cust_id=cust_id, rgs_dt=yyyymmdd)
        .values("mood")
        .annotate(cnt=Count("mood"))
    )

    counts = {"pos": 0, "neu": 0, "neg": 0}
    for row in qs:
        m = row.get("mood")
        if m in counts:
            counts[m] = int(row.get("cnt", 0))

    pos_count = counts["pos"]
    rest_count = counts["neu"] + counts["neg"]
    total = pos_count + rest_count

    if total <= 0:
        return None

    pos_pct = round((pos_count / total) * 100)

    return {
        "rgs_dt": yyyymmdd,
        "pos_count": pos_count,
        "rest_count": rest_count,
        "total": total,
        "pos_pct": pos_pct,
    }

@login_required(login_url="accounts_app:user_login")
def index(request):
    try:
        cust_id = _safe_get_cust_id(request)
    except Exception as e:
        # ✅ 여기서 터지면: 로그인 성공 후 세션/쿠키/유저 매핑 문제
        return HttpResponse(f"[HOME] _safe_get_cust_id failed: {repr(e)}", status=500)
    print(
        "[HOMEDBG]",
        "path=", getattr(request, "path", None),
        "method=", getattr(request, "method", None),
        "pid=", __import__("os").getpid(),
        "remote_addr=", request.META.get("REMOTE_ADDR"),
        "xff=", request.META.get("HTTP_X_FORWARDED_FOR"),
        "ua=", request.META.get("HTTP_USER_AGENT"),
        "host=", request.get_host() if hasattr(request, "get_host") else None,
        "session_key=", getattr(getattr(request, "session", None), "session_key", None),
        "_auth_user_id=", request.session.get("_auth_user_id") if hasattr(request, "session") else None,
        "session_cust_id=", request.session.get("cust_id") if hasattr(request, "session") else None,
        "user_auth=", getattr(getattr(request, "user", None), "is_authenticated", None),
        "user_email=", getattr(getattr(request, "user", None), "email", None),
        "user_cust_id=", getattr(getattr(request, "user", None), "cust_id", None),
        "cust_id_var=", cust_id,
    )

    try:
        today_ymd = timezone.localdate().strftime("%Y%m%d")
    except Exception as e:
        return HttpResponse(f"[HOME] localdate failed: {repr(e)}", status=500)

    try:
        donut = _build_today_donut(cust_id=cust_id, yyyymmdd=today_ymd)
        daily_report = _build_daily_report_chart(cust_id, today_ymd)
        food_payload = build_today_food_payload(cust_id=cust_id, today_ymd=today_ymd)
        menu_reco = _build_menu_reco_context(cust_id=cust_id)
    except Exception as e:
        print("[HOME] DB build error:", e)
        donut = None
        daily_report = {"rgs_dt": today_ymd, "content": ""}
        food_payload = {"rgs_dt": today_ymd, "slots": []}
        menu_reco = {
            "status_text": "추천 준비 중",
            "title": "",
            "line": "",
            "ymd": today_ymd,
            "is_done": False,
        }

    # ✅ json.dumps에서 터지는 경우도 있어서 별도 방어(중요)
    try:
        food_payload_json = json.dumps(food_payload, ensure_ascii=False)
        today_meals_json = json.dumps(food_payload, ensure_ascii=False)
    except Exception as e:
        return HttpResponse(f"[HOME] json.dumps failed: {repr(e)} | food_payload={type(food_payload)}", status=500)

    context = {
        "menu_reco": menu_reco,
        "today_ymd": today_ymd,
        "daily_report": daily_report,
        "food_payload_json": food_payload_json,
        "today_meals": today_meals_json,
        "donut": donut,
    }
    return render(request, "home.html", context)
    
    
@login_required
def badges_redirect(request):
    # canonical: /settings/badges/
    return redirect(reverse("settings_app:settings_badges"))


def _round_int(x) -> int:
    """무조건 반올림해서 int로"""
    if x is None:
        return 0
    try:
        # Decimal/float/int 모두 대응
        return int(round(float(x)))
    except Exception:
        return 0


def _clamp_nonneg(x: int) -> int:
    """음수면 0으로 clamp"""
    return x if x > 0 else 0


def build_today_food_payload(cust_id: str, today_ymd: str) -> dict:
    """
    Home - 오늘 먹은 것들 payload 생성 (SQL/정책 로직 담당)

    규칙
    - 슬롯: M/L/D 고정 (합산만 보여줌)
    - NULL -> 0
    - 음수 -> 0 clamp
    - kcal 표시:
        DB_kcal > 0 -> DB kcal 표시
        DB_kcal == 0 AND total_g > 0 -> 환산 kcal(반올림 정수) 표시
        DB_kcal == 0 AND total_g == 0 -> '-'
    - 막대: g 비율
    - segment 텍스트: 20% 이상만, 정수 g
    - tooltip: bar 전체 1개 ("탄 23g / 단 10g / 지 0g"), 총 g는 표시하지 않음
    - 빈 슬롯(row_count==0): tooltip 비활성
    """

    slots_meta = {
        "M": "아침",
        "L": "점심",
        "D": "저녁",
    }

    # 기본 슬롯 뼈대(3개 고정)
    slots = {
        k: {
            "time_slot": k,
            "label": v,
            "row_count": 0,
            "db_kcal": 0,
            "carb_g": 0,
            "protein_g": 0,
            "fat_g": 0,
        }
        for k, v in slots_meta.items()
    }

    if not cust_id:
        # cust_id 없으면 빈 슬롯 그대로 반환
        return {"rgs_dt": today_ymd, "slots": [slots["M"], slots["L"], slots["D"]]}

    sql = """
        SELECT
            time_slot,
            SUM(COALESCE(kcal, 0))      AS db_kcal,
            SUM(COALESCE(carb_g, 0))    AS carb_g,
            SUM(COALESCE(protein_g, 0)) AS protein_g,
            SUM(COALESCE(fat_g, 0))     AS fat_g
        FROM CUS_FOOD_TH
        WHERE cust_id = %s
          AND rgs_dt  = %s
          AND time_slot IN ('M','L','D')
        GROUP BY time_slot
        ORDER BY time_slot;
    """

    # ✅ fetchall()은 딱 1번만!
    with connection.cursor() as cursor:
        cursor.execute(sql, [cust_id, today_ymd])
        rows = cursor.fetchall()

    # ✅ 디버그(필요 없으면 나중에 삭제)
    print("[FOOD] cust_id:", cust_id, "today_ymd:", today_ymd)
    print("[FOOD] rows:", rows)

    # rows -> slots에 반영
    for ts, kcal, carb, protein, fat in rows:
        ts = (ts or "").strip().upper()
        if ts not in slots:
            continue

        slots[ts]["row_count"] = 1  # 합산만 보여줄 거라 존재 여부만 1로
        slots[ts]["db_kcal"] = _clamp_nonneg(_round_int(kcal))
        slots[ts]["carb_g"] = _clamp_nonneg(_round_int(carb))
        slots[ts]["protein_g"] = _clamp_nonneg(_round_int(protein))
        slots[ts]["fat_g"] = _clamp_nonneg(_round_int(fat))

    result = []
    threshold = 0.20  # 20% 이상만 텍스트 표시

    for ts in ["M", "L", "D"]:
        s = slots[ts]
        carb = s["carb_g"]
        protein = s["protein_g"]
        fat = s["fat_g"]

        total_g = _clamp_nonneg(carb + protein + fat)

        # 환산 kcal(예외 케이스에서만 표시)
        macro_kcal = _round_int(carb * 4 + protein * 4 + fat * 9)

        # kcal 표시 규칙(확정본)
        if s["db_kcal"] > 0:
            kcal_display = f'{s["db_kcal"]}kcal'
        elif total_g > 0:
            kcal_display = f"{macro_kcal}kcal"
        else:
            kcal_display = "-"

        # g 비율
        if total_g > 0:
            carb_pct = carb / total_g
            protein_pct = protein / total_g
            fat_pct = fat / total_g
        else:
            carb_pct = protein_pct = fat_pct = 0.0

        segments = [
            {
                "key": "carb",
                "label": "탄",
                "g": carb,
                "pct": carb_pct,
                "showText": carb_pct >= threshold,
            },
            {
                "key": "protein",
                "label": "단",
                "g": protein,
                "pct": protein_pct,
                "showText": protein_pct >= threshold,
            },
            {
                "key": "fat",
                "label": "지",
                "g": fat,
                "pct": fat_pct,
                "showText": fat_pct >= threshold,
            },
        ]

        result.append(
            {
                "time_slot": ts,
                "label": s["label"],
                "kcal_display": kcal_display,
                "total_g": total_g,
                "segments": segments,
                # 빈 슬롯이면 tooltip 비활성
                "tooltip_enabled": s["row_count"] > 0,
                "tooltip_text": f"탄 {carb}g / 단 {protein}g / 지 {fat}g",
            }
        )

    return {"rgs_dt": today_ymd, "slots": result}
