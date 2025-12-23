from django.shortcuts import render, redirect
from datetime import date, datetime, timedelta
from django.db import connection
import json
from report.views import get_selected_date
from django.db import connection
from decimal import Decimal

# Create your views here.
def record_mood(request):
    selected_date = get_selected_date(request)
    context = {"selected_date": selected_date.strftime("%Y-%m-%d")}
    user_id = request.user.cust_id

    if request.method == "POST":
        mood = request.POST['mood']
        energy = request.POST['energy']
        keyword = request.POST['keyword'].split(',')
        date_time = selected_date.strftime("%Y%m%d%H%M%S")
        rgs_dt = selected_date.strftime("%Y%m%d")

        print(mood, energy, keyword, date_time, rgs_dt, user_id)

        sql = """
        INSERT VALUES
        FROM CUS_FEEL_TH
        VALUES (%s, %s, %s, %s, %d, %s, %s, %s, %s, %s)
        """

        #
        # with connection.cursor() as cursor:
        #     cursor.execute(sql, [cust_id, start, end])
        #     rows = cursor.fetchall()

        return redirect("/record/meal/")
    else:
        return render(request, "record/record_mood.html", context)

def record_meal(request):
    return render(request, "record/record_meal.html")

def recipe_search(request):
    return render(request, "record/recipe_search.html")


def recipe_new(request):
    return render(request, "record/recipe_new.html")


def camera(request):
    return render(request, "record/camera.html")


def scan_result(request):
    return render(request, "record/scan_result.html")


def timeline(request):
    """
    감정 변화 요약 (주간)
    - 막대 높이 = 하루 총 감정 강도 합 (0~9)
    - 누적 색 = 긍/중/부정 강도 구성
    """

    cust_id = "1000000001"

    # 1) 기간 파라미터
    start = request.GET.get("start")
    end = request.GET.get("end")

    today = datetime.now().date()

    if not end:
        end_date = today
        end = end_date.strftime("%Y%m%d")
    else:
        end_date = datetime.strptime(end, "%Y%m%d").date()

    if not start:
        start_date = end_date - timedelta(days=6)
        start = start_date.strftime("%Y%m%d")
    else:
        start_date = datetime.strptime(start, "%Y%m%d").date()

    week_start = start_date.strftime("%Y.%m.%d")
    week_end = end_date.strftime("%Y.%m.%d")

    # 2) SQL: 하루 1행, score 그대로 사용
    sql = """
    SELECT
      rgs_dt,
      COALESCE(pos_count, 0) AS pos_score,
      COALESCE(neu_count, 0) AS neu_score,
      COALESCE(neg_count, 0) AS neg_score
    FROM CUS_FEEL_RATIO_TH
    WHERE cust_id = %s
      AND rgs_dt BETWEEN %s AND %s
    ORDER BY rgs_dt;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, [cust_id, start, end])
        rows = cursor.fetchall()

    # 3) 날짜 → score 매핑
    day_to_score = {}
    for rgs_dt, pos_s, neu_s, neg_s in rows:
        day_to_score[rgs_dt] = (
            int(pos_s or 0),
            int(neu_s or 0),
            int(neg_s or 0),
        )

    # 4) 7일 고정 생성
    labels, pos, neu, neg = [], [], [], []

    cur = start_date
    while cur <= end_date:
        key = cur.strftime("%Y%m%d")
        labels.append(f"{cur.month}/{cur.day}")

        p, n, g = day_to_score.get(key, (0, 0, 0))
        pos.append(p)
        neu.append(n)
        neg.append(g)

        cur += timedelta(days=1)

    chart_json = json.dumps(
        {
            "labels": labels,
            "pos": pos,
            "neu": neu,
            "neg": neg,
            "y_max": 9,  # ✅ 고정 스케일
        },
        ensure_ascii=False,
    )

    context = {
        "active_tab": "timeline",
        "week_start": week_start,
        "week_end": week_end,
        "chart_json": chart_json,
        "risk_label": "위험해요ㅠㅠ",
        "risk_score": 0.78,
        "llm_ment": "오늘은 기분이 좋지 않았네요. 가벼운 산책은 어때요?",
    }

    return render(request, "timeline.html", context)


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
            {"key": "carb", "label": "탄", "g": carb, "pct": carb_pct, "showText": carb_pct >= threshold},
            {"key": "protein", "label": "단", "g": protein, "pct": protein_pct, "showText": protein_pct >= threshold},
            {"key": "fat", "label": "지", "g": fat, "pct": fat_pct, "showText": fat_pct >= threshold},
        ]

        result.append({
            "time_slot": ts,
            "label": s["label"],
            "kcal_display": kcal_display,
            "total_g": total_g,
            "segments": segments,

            # 빈 슬롯이면 tooltip 비활성
            "tooltip_enabled": s["row_count"] > 0,
            "tooltip_text": f"탄 {carb}g / 단 {protein}g / 지 {fat}g",
        })

    return {"rgs_dt": today_ymd, "slots": result}