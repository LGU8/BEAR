from django.http import HttpResponseBadRequest
from django.shortcuts import render, redirect
from datetime import date, datetime, timedelta
from django.db import connection
import json
from report.views import get_selected_date


# Create your views here.
def record_mood(request):
    selected_date = get_selected_date(request)
    context = {"selected_date": selected_date.strftime("%Y-%m-%d"),
               "active_tab": "record",}

    if request.method == "POST":
        time_slot = request.POST['time_slot']
        mood = request.POST['mood']
        energy = request.POST['energy']
        keyword = request.POST['keyword'].split(',')
        date_time = selected_date.strftime("%Y%m%d%H%M%S")
        rgs_dt = selected_date.strftime("%Y%m%d")
        cust_id = request.user.cust_id
        stable_yn = 1 if (mood in ('pos','neu') and energy in ('low', 'med')) else 0

        if not time_slot or not mood or not energy:
            return HttpResponseBadRequest("시간, 감정, 활성도는 필수 항목입니다.")

        # seq 가져오기
        sql = """
        SELECT COALESCE(MAX(seq), 0) + 1
        FROM CUS_FEEL_TH
        WHERE cust_id = %s
        """
        data = [cust_id]

        with connection.cursor() as cursor:
            cursor.execute(sql, data)
            seq = cursor.fetchone()[0]

        sql = """
        INSERT INTO CUS_FEEL_TH (
            created_time, updated_time, cust_id, rgs_dt, seq, time_slot, mood, energy, cluster_val, stable_yn
        )
        VALUES(
            %s, %s, %s, %s, %s, %s, %s, %s,
            (SELECT cluster_val
                FROM COM_FEEL_CLUSTER_TM
                WHERE mood = %s AND energy = %s),
            %s)
        """

        FEEL_TH = [
            # FEEL_TH
            date_time, date_time, cust_id, rgs_dt, seq, time_slot, mood, energy,
            mood, energy,
            stable_yn
        ]

        with connection.cursor() as cursor:
            cursor.execute(sql, FEEL_TH)

        if keyword != ['']:
            for k in keyword:
                sql = """
                INSERT INTO CUS_FEEL_TS (
                    created_time, updated_time, cust_id, rgs_dt, seq, keyword_seq, feel_id
                )
                SELECT
                    %s, %s, %s, %s, %s,
                    COALESCE(MAX(keyword_seq), 0) + 1,
                    (SELECT feel_id
                        FROM COM_FEEL_TM
                        WHERE word = %s)
                FROM CUS_FEEL_TS
                WHERE cust_id = %s
                AND seq = %s
                """

                FEEL_TS = [
                    date_time, date_time, cust_id, rgs_dt, seq,
                    k,
                    cust_id, seq
                ]

                with connection.cursor() as cursor:
                    cursor.execute(sql, FEEL_TS)
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

