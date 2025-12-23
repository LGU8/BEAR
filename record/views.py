from django.http import HttpResponseBadRequest
from django.shortcuts import render, redirect
from datetime import date, datetime, timedelta
from django.db import connection
import json
from report.views import get_selected_date
from conf.views import _safe_get_cust_id
from django.utils import timezone


# Create your views here.
def record_mood(request):
    selected_date = get_selected_date(request)
    context = {"selected_date": selected_date.strftime("%Y-%m-%d"),
               "active_tab": "record",}

    if request.method == "POST":
        time_slot = request.POST["time_slot"]
        mood = request.POST["mood"]
        energy = request.POST["energy"]
        keyword = request.POST["keyword"].split(",")
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

        # CUS_FEEL_TH 저장
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

        # CUS_FEEL_TS 저장
        if keyword != ['']:
            FEEL_TS = []
            for i, k in enumerate(keyword):
                keyword_seq = i+1
                sql = """
                INSERT INTO CUS_FEEL_TS (
                    created_time, updated_time, cust_id, rgs_dt, seq, keyword_seq, feel_id
                )
                VALUES(
                    %s, %s, %s, %s, %s, %s,
                    (SELECT feel_id
                        FROM COM_FEEL_TM
                        WHERE word = %s))
                """

                row_data = (date_time, date_time, cust_id, rgs_dt, seq, keyword_seq, k)
                FEEL_TS.append(row_data)

            with connection.cursor() as cursor:
                cursor.executemany(sql, FEEL_TS)
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
    - 막대 높이 = 하루 총 감정 강도 합
    - 누적 색 = 긍/중/부정 강도 구성
    - 점수 산정:
        energy: hig=3, med=2, low=1
        mood(pos/neu/neg)에 따라 각 score로 누적
    """

    # ✅ home(index)와 동일한 방식으로 cust_id 결정
    cust_id = _safe_get_cust_id(request)

    # 1) 기간 파라미터
    start = request.GET.get("start")
    end = request.GET.get("end")

    today = timezone.localdate()

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

    # 2) SQL: CUS_FEEL_TH에서 mood+energy로 score 산정 후, 하루 1행 집계
    sql = """
    SELECT
      rgs_dt,
      SUM(
        CASE WHEN mood = 'pos' THEN
          CASE energy
            WHEN 'hig' THEN 3
            WHEN 'med' THEN 2
            WHEN 'mid' THEN 2
            WHEN 'low' THEN 1
            ELSE 0
          END
        ELSE 0 END
      ) AS pos_score,
      SUM(
        CASE WHEN mood = 'neu' THEN
          CASE energy
            WHEN 'hig' THEN 3
            WHEN 'med' THEN 2
            WHEN 'mid' THEN 2
            WHEN 'low' THEN 1
            ELSE 0
          END
        ELSE 0 END
      ) AS neu_score,
      SUM(
        CASE WHEN mood = 'neg' THEN
          CASE energy
            WHEN 'hig' THEN 3
            WHEN 'med' THEN 2
            WHEN 'mid' THEN 2
            WHEN 'low' THEN 1
            ELSE 0
          END
        ELSE 0 END
      ) AS neg_score
    FROM CUS_FEEL_TH
    WHERE cust_id = %s
      AND rgs_dt BETWEEN %s AND %s
    GROUP BY rgs_dt
    ORDER BY rgs_dt;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, [cust_id, start, end])
        rows = cursor.fetchall()

    # 3) 날짜 → score 매핑
    day_to_score = {}
    for rgs_dt, pos_s, neu_s, neg_s in rows:
        day_to_score[str(rgs_dt)] = (
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
            "y_max": 9,  # 기존 고정 스케일 유지
        },
        ensure_ascii=False,
    )

    context = {
        "active_tab": "timeline",
        "week_start": week_start,
        "week_end": week_end,
        "chart_json": chart_json,
        # 아래 3개는 네 기존 context에 있던 값이면 유지, 아니면 제거 가능
        "risk_label": "위험해요ㅠㅠ",
        "risk_score": 0.78,
        "llm_ment": "오늘은 기분이 좋지 않았네요. 가벼운 산책은 어때요?",
    }

    return render(request, "timeline.html", context)
