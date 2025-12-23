from django.shortcuts import render
from datetime import date, datetime, timedelta
from django.db import connection
import json
from report.views import get_selected_date


# Create your views here.
def record_mood(request):
    selected_date = get_selected_date(request)
    context = {"selected_date": selected_date.strftime("%Y-%m-%d")}
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

