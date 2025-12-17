from django.shortcuts import render
from datetime import date, datetime, timedelta
from django.db import connection
import json

# Create your views here.
def record_index(request):
    return render(request, "record/record_index.html")


def recipe_search(request):
    return render(request, "record/recipe_search.html")


def recipe_new(request):
    return render(request, "record/recipe_new.html")


def camera(request):
    return render(request, "record/camera.html")


def scan_result(request):
    return render(request, "record/scan_result.html")


def api_scan(request):
    return render(request, "record/scan_result.html")


def timeline(request):
    """
    /timeline
    - GET 파라미터:
      - start: YYYYMMDD (선택)
      - end:   YYYYMMDD (선택)
    - 조회 기준:
      - CUS_FEEL_RATIO_TH.updated_time(YYYYMMDDHHMMSS)의 앞 8자리(YYYYMMDD)를 day_key로 사용
      - updated_time이 NULL이면 rgs_dt로 fallback
    - 출력:
      - 날짜별 pos/neu/neg 비율(0~100)을 stacked bar로 표시할 수 있도록 chart_json을 내려줌
    """

    # TODO: 로그인 연동 전 임시 cust_id
    cust_id = "1000000001"

    # 1) 기간 파라미터 받기 (YYYYMMDD)
    start = request.GET.get("start")
    end = request.GET.get("end")

    # 2) 기본값: 오늘 기준 최근 7일
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

    # 화면 표시용 (YYYY.MM.DD)
    week_start = start_date.strftime("%Y.%m.%d")
    week_end = end_date.strftime("%Y.%m.%d")

    # 3) SQL: updated_time 날짜(앞 8자리) 기준으로 필터/그룹핑
    #    - ratio 컬럼이 테이블에 있어도 "합산 ratio"는 의미가 없어서
    #      count를 합산하고 ratio를 재계산하는 방식으로 구현
    sql = """
    SELECT
      day_key,
      SUM(pos_count) AS pos_count,
      SUM(neu_count) AS neu_count,
      SUM(neg_count) AS neg_count,
      CASE
        WHEN (SUM(pos_count) + SUM(neu_count) + SUM(neg_count)) = 0 THEN 0
        ELSE ROUND(SUM(pos_count) * 100.0 / (SUM(pos_count) + SUM(neu_count) + SUM(neg_count)), 1)
      END AS pos_ratio,
      CASE
        WHEN (SUM(pos_count) + SUM(neu_count) + SUM(neg_count)) = 0 THEN 0
        ELSE ROUND(SUM(neu_count) * 100.0 / (SUM(pos_count) + SUM(neu_count) + SUM(neg_count)), 1)
      END AS neu_ratio,
      CASE
        WHEN (SUM(pos_count) + SUM(neu_count) + SUM(neg_count)) = 0 THEN 0
        ELSE ROUND(SUM(neg_count) * 100.0 / (SUM(pos_count) + SUM(neu_count) + SUM(neg_count)), 1)
      END AS neg_ratio
    FROM (
      SELECT
        COALESCE(SUBSTR(updated_time, 1, 8), rgs_dt) AS day_key,
        COALESCE(pos_count, 0) AS pos_count,
        COALESCE(neu_count, 0) AS neu_count,
        COALESCE(neg_count, 0) AS neg_count
      FROM CUS_FEEL_RATIO_TH
      WHERE cust_id = %s
    ) t
    WHERE day_key BETWEEN %s AND %s
    GROUP BY day_key
    ORDER BY day_key;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, [cust_id, start, end])
        rows = cursor.fetchall()

    # 4) 차트 데이터 만들기
    # rows: (day_key, pos_count, neu_count, neg_count, pos_ratio, neu_ratio, neg_ratio)
    labels, pos, neu, neg = [], [], [], []
    for (day_key, _pc, _nc, _gc, pr, nr, gr) in rows:
        labels.append(f"{day_key[0:4]}.{day_key[4:6]}.{day_key[6:8]}")
        pos.append(float(pr))
        neu.append(float(nr))
        neg.append(float(gr))

    # 5) 템플릿 → JS 안전 전달용 JSON 문자열
    chart_json = json.dumps(
        {
            "labels": labels,
            "pos": pos,
            "neu": neu,
            "neg": neg,
        },
        ensure_ascii=False
    )

    # 6) context
    context = {
        "active_tab": "timeline",
        "week_start": week_start,
        "week_end": week_end,

        "chart_json": chart_json,

        # 아직은 더미 (나중에 ML/LLM 붙이면 DB에서 읽거나 추론 결과로 교체)
        "risk_label": "위험해요ㅠㅠ",
        "risk_score": 0.78,
        "llm_ment": "오늘은 기분이 좋지 않았네요. 달리기/걷기/음악듣기 중 하나를 해보는 건 어때요?",
    }

    return render(request, "timeline.html", context)
