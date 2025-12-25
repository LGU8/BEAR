from django.http import HttpResponseBadRequest
from django.shortcuts import render, redirect
from datetime import date, datetime, timedelta
from django.db import connection, transaction
import json
from report.views import get_selected_date
from conf.views import _safe_get_cust_id
from django.utils import timezone
from ml.lstm.predictor import predict_negative_risk
from django.utils import timezone


# Create your views here.
def record_mood(request):
    selected_date = get_selected_date(request)
    context = {
        "selected_date": selected_date.strftime("%Y-%m-%d"),
        "active_tab": "record",
    }

    if request.method != "POST":
        return render(request, "record/record_mood.html", context)

    # 입력값 정리
    time_slot = request.POST.get("time_slot")
    mood = request.POST.get("mood")
    energy = request.POST.get("energy")
    keyword_raw = request.POST.get("keyword", "")
    keywords = [k for k in keyword_raw.split(",") if k]

    if not time_slot or not mood or not energy:
        return HttpResponseBadRequest("시간, 감정, 활성도는 필수 항목입니다.")

    cust_id = request.user.cust_id
    rgs_dt = selected_date.strftime("%Y%m%d")
    date_time = selected_date.strftime("%Y%m%d%H%M%S")
    stable_yn = "y" if (mood in ("pos", "neu") and energy in ("low", "med")) else "n"

    # 트랜잭션 시작
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:

                # 기존 기록 존재 여부 확인
                cursor.execute(
                    """
                    SELECT seq
                    FROM CUS_FEEL_TH
                    WHERE cust_id = %s
                      AND rgs_dt = %s
                      AND time_slot = %s
                    """,
                    [cust_id, rgs_dt, time_slot],
                )
                row = cursor.fetchone()

                # INSERT 경로
                if row is None:
                    cursor.execute(
                        """
                        SELECT COALESCE(MAX(seq), 0) + 1
                        FROM CUS_FEEL_TH
                        WHERE cust_id = %s
                        """,
                        [cust_id],
                    )
                    seq = cursor.fetchone()[0]

                    cursor.execute(
                        """
                        INSERT INTO CUS_FEEL_TH (
                            created_time, updated_time, cust_id,
                            rgs_dt, seq, time_slot,
                            mood, energy, cluster_val, stable_yn
                        )
                        VALUES (
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            (SELECT cluster_val
                               FROM COM_FEEL_CLUSTER_TM
                              WHERE mood = %s AND energy = %s),
                            %s
                        )
                        """,
                        [
                            date_time, date_time, cust_id,
                            rgs_dt, seq, time_slot,
                            mood, energy,
                            mood, energy,
                            stable_yn,
                        ],
                    )

                # UPDATE 경로
                else:
                    seq = row[0]

                    cursor.execute(
                        """
                        UPDATE CUS_FEEL_TH
                        SET
                            updated_time = %s, mood = %s, energy = %s,
                            cluster_val = (SELECT cluster_val
                                             FROM COM_FEEL_CLUSTER_TM
                                            WHERE mood = %s AND energy = %s),
                            stable_yn = %s
                        WHERE cust_id = %s
                          AND rgs_dt = %s
                          AND time_slot = %s
                        """,
                        [
                            date_time, mood, energy,
                            mood, energy,
                            stable_yn,
                            cust_id, rgs_dt, time_slot,
                        ],
                    )

                    # 기존 키워드 삭제
                    cursor.execute(
                        """
                        DELETE FROM CUS_FEEL_TS
                        WHERE cust_id = %s
                          AND rgs_dt = %s
                          AND seq = %s
                        """,
                        [cust_id, rgs_dt, seq],
                    )

                # 키워드 재삽입
                if keywords:
                    ts_rows = []
                    for i, k in enumerate(keywords, start=1):
                        ts_rows.append(
                            (date_time, date_time, cust_id, rgs_dt, seq, i, k)
                        )

                    cursor.executemany(
                        """
                        INSERT INTO CUS_FEEL_TS (
                            created_time, updated_time, cust_id,
                            rgs_dt, seq, keyword_seq, feel_id
                        )
                        VALUES (
                            %s, %s, %s,
                            %s, %s, %s,
                            (SELECT feel_id
                               FROM COM_FEEL_TM
                              WHERE word = %s)
                        )
                        """,
                        ts_rows,
                    )

        # 트랜잭션 정상 종료 → commit
    except Exception as e:
        return HttpResponseBadRequest(f"저장 중 오류 발생: {e}")

    # meal.html에 데이터 전송
    request.session["rgs_dt"] = rgs_dt
    request.session["seq"] = seq
    request.session["time_slot"] = time_slot
    return redirect("/record/meal/")


def record_meal(request):
    cust_id = request.user.cust_id
    rgs_dt = request.session.get("rgs_dt")
    seq = request.session.get("seq")
    time_slot = request.session.get("time_slot")
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
   
   # 기준일 D (최신 기록일)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT MAX(rgs_dt) FROM CUS_FEEL_TH WHERE cust_id = %s",
            [cust_id]
        )
        row = cursor.fetchone()

    D_str = str(row[0]) if row and row[0] else timezone.localdate().strftime("%Y%m%d")
    D_date = datetime.strptime(D_str, "%Y%m%d").date()

    neg_pred = predict_negative_risk(cust_id=cust_id, D_yyyymmdd=D_str)

    # ✅ 예측 결과 DB 저장
    if neg_pred.get("eligible"):
        now_ts = timezone.localtime().strftime("%Y%m%d%H%M%S")

        # ⭐ 핵심: D의 다음날 아침(M)
        target_date = (D_date + timedelta(days=1)).strftime("%Y%m%d")
        target_slot = "M"

        p_high = float(neg_pred.get("p_highrisk") or 0.0)
        risk_score = int(round(p_high * 100))
        risk_level = "y" if risk_score >= 30 else "n"

        upsert_sql = """
        INSERT INTO CUS_FEEL_RISK_TH (
            created_time, updated_time,
            cust_id, rgs_dt, time_slot,
            risk_score, risk_level
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            updated_time = VALUES(updated_time),
            risk_score   = VALUES(risk_score),
            risk_level   = VALUES(risk_level);
        """

        with connection.cursor() as cursor:
            cursor.execute(
                upsert_sql,
                [now_ts, now_ts, cust_id, target_date, target_slot, risk_score, risk_level]
            )

   



    
    # =========================
    # (추가) UI용 상태 계산
    #  - ui_active_idx: 0=긍정, 1=중립, 2=부정
    #  - ui_status_text: 상태 문구
    # =========================
    neg_pred["ui_active_idx"] = 1
    neg_pred["ui_status_text"] = "예측 준비 중"

    if neg_pred.get("eligible", False):
        p = neg_pred.get("p_highrisk", 0.0)
        try:
            p = float(p)
        except (TypeError, ValueError):
            p = 0.0

        if p >= 0.30:
            neg_pred["ui_active_idx"] = 2
            neg_pred["ui_status_text"] = "위험해요ㅠㅠ"
        elif p >= 0.20:
            neg_pred["ui_active_idx"] = 1
            neg_pred["ui_status_text"] = "조심해요"
        else:
            neg_pred["ui_active_idx"] = 0
            neg_pred["ui_status_text"] = "안정적이에요"

    context = {
        "active_tab": "timeline",
        "week_start": week_start,
        "week_end": week_end,
        "chart_json": chart_json,
        "neg_pred": neg_pred,
        # 아래 3개는 네 기존 context에 있던 값이면 유지, 아니면 제거 가능
        "risk_label": "위험해요ㅠㅠ",
        "risk_score": 0.78,
        "llm_ment": "오늘은 기분이 좋지 않았네요. 가벼운 산책은 어때요?",
    }

    return render(request, "timeline.html", context)
