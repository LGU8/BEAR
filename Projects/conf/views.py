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


def public_home(request):
    # ✅ DB/세션/로그인 의존 없이 렌더만 되는 템플릿
    # home.html을 그대로 쓰면 내부에서 context 기대할 수 있으니
    # public 전용 템플릿을 하나 두는 게 안전
    return render(request, "public_home.html")


def _safe_get_cust_id(request) -> str:
    """
    ✅ 로그인 구현을 건드리지 않고,
    '현재 로그인 사용자'에서 cust_id로 쓸 수 있는 후보를 안전하게 찾는다.

    우선순위:
    1) 세션에 cust_id가 있으면 그걸 최우선 (가장 안전)
    2) request.user.username
    3) request.user.email
    4) request.user에 cust_id 속성이 직접 있는 경우
    """
    # 1) session
    cust_id = request.session.get("cust_id")
    if cust_id:
        return str(cust_id)

    if request.user.is_authenticated and getattr(request.user, "cust_id", None):
        return str(request.user.cust_id)

    if request.user.is_authenticated and getattr(request.user, "username", None):
        return str(request.user.username)

    if request.user.is_authenticated and getattr(request.user, "email", None):
        return str(request.user.email)

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


def _build_menu_reco_context(cust_id: str) -> dict:
    """
    ✅ 최종 정책(네가 방금 확정한 것 반영)

    - 기본 조회 날짜는 무조건 오늘(KST 캘린더 날짜) rgs_dt
    - 다음 slot 판단은 CUS_FOOD_TH & CUS_FEEL_TH의 (오늘, slot) 동시 존재로 판정
    - 단, '어제(D 완료)' 상태가 있고 지금 시간이 새벽 4시 이전이면:
        -> "오늘 식사 기록이 모두 완료됐어요. 추천 준비 중" 유지
        -> (새로운 하루 추천 시작 안 함)
      (즉, 4시가 지나면 자연스럽게 오늘 날짜로 새로 시작)

    - 추천은 MENU_RECOM_TH(오늘, next_slot)에서 P/H/E를 FOOD_TB와 조인해서
      성공한 것만 문구로 출력
    - 조인 결과 0개면 "추천 준비 중"
    """
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

    # 1) 새벽 4시 이전에는 "어제 완료" 상태를 유지(오늘 추천 시작 X)
    if _is_before_4am_kst():
        y_slot_or_done, _ = _next_slot_by_food_and_feel(cust_id, yesterday_ymd)
        if y_slot_or_done == "DONE":
            base["is_done"] = True
            base["status_text"] = "오늘 식사 기록이 모두 완료됐어요. 추천 준비 중"
            base["title"] = ""
            base["line"] = ""
            return base
        # 어제가 DONE이 아니면 -> 오늘 기준으로 정상 진행(테스트 데이터가 00시대여도 오늘로 조회됨)

    # 2) 오늘 기준으로 다음 slot 결정
    slot_or_done, _ = _next_slot_by_food_and_feel(cust_id, today_ymd)

    # 오늘 DONE이면: 완료 문구 출력(너 요구대로)
    if slot_or_done == "DONE":
        base["is_done"] = True
        base["status_text"] = "오늘 식사 기록이 모두 완료됐어요. 추천 준비 중"
        return base

    # 정님 코드
    # target_slot = slot_or_done
    # slot_label = {"M": "아침", "L": "점심", "D": "저녁"}[target_slot]
    # base["title"] = f"{slot_label} 메뉴 추천"

    # -------------------------------------------------------
    # ✅ 핵심 변경:
    # - reco_key_slot: MENU_RECOM_TH.rec_time_slot 조회용 (마지막 완료 슬롯)
    # - display_slot: 화면에 표기할 추천 대상 슬롯 (다음 슬롯)
    # -------------------------------------------------------
    reco_key_slot = _last_done_slot_by_food_and_feel(cust_id, today_ymd)
    if not reco_key_slot:
        base["status_text"] = "추천 준비 중"
        return base

    display_slot = _recommend_target_slot_from_trigger_slot(reco_key_slot)
    if display_slot == "DONE":
        base["is_done"] = True
        base["status_text"] = "오늘 식사 기록이 모두 완료됐어요. 추천 준비 중"
        return base

    slot_label = {"M": "아침", "L": "점심", "D": "저녁"}[display_slot]
    base["title"] = f"{slot_label} 메뉴 추천"

    # 3) 추천 로딩 (오늘 + reco_key_slot)
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
        cursor.execute(sql_reco, [cust_id, today_ymd, reco_key_slot])
        rows = cursor.fetchall()

    if not rows:
        base["status_text"] = "추천 준비 중"
        return base

    type_label = {"P": "취향 기반", "H": "균형(5:3:2)", "E": "새로운 메뉴"}

    parts = []
    for rec_type, food_id, food_name in rows:
        t = str(rec_type).strip().upper()
        nm = str(food_name).strip() if food_name is not None else ""
        if not nm:
            continue
        parts.append(f"{type_label.get(t, t)}: {nm}")

    if not parts:
        base["status_text"] = "추천 준비 중"
        return base

    print(
        "[menu_reco] cust_id=", cust_id,
        "today_ymd=", today_ymd,
        "reco_key_slot=", reco_key_slot,
        "display_slot=", display_slot,
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


@login_required(login_url="/")
def index(request):
    cust_id = _safe_get_cust_id(request)
    today_ymd = timezone.localdate().strftime("%Y%m%d")

    try:
        donut = _build_today_donut(cust_id=cust_id, yyyymmdd=today_ymd)
        daily_report = _build_daily_report_chart(cust_id, today_ymd)
        food_payload = build_today_food_payload(cust_id=cust_id, today_ymd=today_ymd)
        menu_reco = _build_menu_reco_context(cust_id=cust_id)
    except Exception as e:
        # ✅ EC2 초기 스키마/권한/테이블 미세팅 상태에서 500 방지
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

    context = {
        "menu_reco": menu_reco,
        "today_ymd": today_ymd,
        "daily_report": daily_report,
        "food_payload_json": json.dumps(food_payload, ensure_ascii=False),
        "today_meals": json.dumps(food_payload, ensure_ascii=False),
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
