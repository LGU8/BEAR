from django.http import HttpResponseBadRequest
from django.shortcuts import render, redirect
from datetime import date, datetime, timedelta
from django.db import connection, transaction
import json
from report.views import get_selected_date
from conf.views import _safe_get_cust_id
from django.utils import timezone
from ml.lstm.predictor import predict_negative_risk
from django.db import connection
from ml.behavior_llm.behavior_service import generate_and_save_behavior_recom
import traceback

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
                            date_time,
                            date_time,
                            cust_id,
                            rgs_dt,
                            seq,
                            time_slot,
                            mood,
                            energy,
                            mood,
                            energy,
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
                            date_time,
                            mood,
                            energy,
                            mood,
                            energy,
                            stable_yn,
                            cust_id,
                            rgs_dt,
                            time_slot,
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


def _exists_feel_on_date(cust_id: str, rgs_dt: str) -> bool:
    sql = """
        SELECT 1
        FROM CUS_FEEL_TH
        WHERE cust_id = %s AND rgs_dt = %s
        LIMIT 1
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [cust_id, rgs_dt])
        return cursor.fetchone() is not None


def _pick_source_date_today_or_yesterday(cust_id: str) -> str | None:
    """
    source_date 선택 정책(고정):
    - 오늘 기록 있으면 오늘
    - 없으면 어제 기록 있으면 어제
    - 둘 다 없으면 None
    """
    today = timezone.localdate()
    today_ymd = today.strftime("%Y%m%d")
    yest_ymd = (today - timedelta(days=1)).strftime("%Y%m%d")

    if _exists_feel_on_date(cust_id, today_ymd):
        return today_ymd
    if _exists_feel_on_date(cust_id, yest_ymd):
        return yest_ymd
    return None


def _pick_source_slot_DLM(cust_id: str, rgs_dt: str) -> str | None:
    """
    같은 rgs_dt 내 최신 slot 정책(고정): D > L > M
    """
    sql = """
        SELECT time_slot
        FROM CUS_FEEL_TH
        WHERE cust_id = %s AND rgs_dt = %s
        GROUP BY time_slot
    """
    with connection.cursor() as cursor:
        cursor.execute(sql, [cust_id, rgs_dt])
        slots = {str(r[0]).upper() for r in cursor.fetchall() if r and r[0]}

    if "D" in slots:
        return "D"
    if "L" in slots:
        return "L"
    if "M" in slots:
        return "M"
    return None


def _target_from_source(source_date_ymd: str, source_slot: str) -> tuple[str, str]:
    """
    다음 슬롯(target) 전이 정책(고정):
    - M -> 같은날 L
    - L -> 같은날 D
    - D -> 다음날 M
    """
    s = source_slot.upper()
    if s == "M":
        return (source_date_ymd, "L")
    if s == "L":
        return (source_date_ymd, "D")

    # D(또는 기타) -> 다음날 M
    d = datetime.strptime(source_date_ymd, "%Y%m%d").date()
    next_ymd = (d + timedelta(days=1)).strftime("%Y%m%d")
    return (next_ymd, "M")


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
    # =========================
    # (2) 부정 감정 예측: source(today/어제) -> target(다음 슬롯)
    # =========================

    source_date = _pick_source_date_today_or_yesterday(cust_id)

    today_ymd = timezone.localdate().strftime("%Y%m%d")
    yest_ymd = (timezone.localdate() - timedelta(days=1)).strftime("%Y%m%d")

    if source_date is None:
        neg_pred = {
            "eligible": False,
            "reason": "데이터가 없습니다",
            "detail": {
                "type": "no_recent_record",
                "rule": "오늘/어제 중 감정 기록이 있어야 예측 가능합니다",
                "asof": today_ymd,
                # ✅ 정확히 '어느 날짜 데이터가 없음'인지 명시
                "missing_days": [yest_ymd, today_ymd],
            },
        }
        target_date, target_slot = None, None

    else:
        source_slot = _pick_source_slot_DLM(cust_id, source_date)

        if source_slot is None:
            # source_date는 있는데 slot이 없다? (이론상 거의 없음) -> 데이터 없음 처리
            neg_pred = {
                "eligible": False,
                "reason": "데이터가 없습니다",
                "detail": {
                    "type": "no_recent_record",
                    "rule": "오늘/어제 중 감정 기록이 있어야 예측 가능합니다",
                    "asof": source_date,
                },
            }
            target_date, target_slot = None, None

        else:
            # target 계산(다음 슬롯)
            target_date, target_slot = _target_from_source(source_date, source_slot)

            # ✅ 예측은 source_date 기준으로 수행
            neg_pred = predict_negative_risk(cust_id=cust_id, D_yyyymmdd=source_date)

            # predictor 호출 직후(neg_pred 만든 다음) 템플릿 안정화
            if not neg_pred.get("eligible", False):
                detail = neg_pred.get("detail") or {}
                md = detail.get("missing_days")
                if md is None:
                    md = neg_pred.get("missing_days", [])
                if not isinstance(md, list):
                    md = []
                # 둘 다에 동기화
                detail["missing_days"] = md
                neg_pred["missing_days"] = md
                neg_pred["detail"] = detail

            # ✅ 예측 결과 DB 저장(저장은 target 키로)
            if neg_pred.get("eligible"):
                now_ts = timezone.localtime().strftime("%Y%m%d%H%M%S")

                p_high = float(neg_pred.get("p_highrisk") or 0.0)
                risk_score = int(round(p_high * 100))
                # UI/정책 기준(p0+p2>=0.30)과 1:1 매칭: risk_score>=30
                risk_level = "y" if risk_score >= 30 else "n"

                upsert_sql = """
                INSERT INTO CUS_FEEL_RISK_TH (
                    created_time, updated_time,
                    cust_id, target_date, target_slot,
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
                        [
                            now_ts,
                            now_ts,
                            cust_id,
                            target_date,
                            target_slot,
                            risk_score,
                            risk_level,
                        ],
                    )
                try:
                    generate_and_save_behavior_recom(
                        cust_id=cust_id,
                        target_date=target_date,
                        target_slot=target_slot,
                    )
                except Exception as e:
                    print("### 행동추천 생성 실패 ###")
                    print(e)
                    traceback.print_exc()

    # =========================
    # (추가) UI용 상태 계산(기존 유지 + 데이터 없음 케이스 보강)
    # =========================
    neg_pred["ui_active_idx"] = 1
    neg_pred["ui_status_text"] = "예측 준비 중"

    if not neg_pred.get("eligible", False):
        # ✅ 오늘/어제 기록 자체가 없음
        if neg_pred.get("detail", {}).get("type") == "no_recent_record":
            neg_pred["ui_active_idx"] = 1
            neg_pred["ui_status_text"] = "데이터 없음"
    else:
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
    # (여기까지: chart_json 만들고, neg_pred 만들고, ui_active_idx/ui_status_text까지 세팅 완료된 상태)

     # =========================
    # (추가) 행동추천 멘트 조회: CUS_BEH_RECOM_TH.content → llm_ment
    # =========================
    llm_ment = ""

    if target_date and target_slot:
        sql_recom = """
            SELECT content
            FROM CUS_BEH_RECOM_TH
            WHERE cust_id = %s
              AND target_date = %s
              AND target_slot = %s
            LIMIT 1
        """
        with connection.cursor() as cursor:
            cursor.execute(sql_recom, [cust_id, target_date, target_slot])
            row = cursor.fetchone()
            if row and row[0]:
                llm_ment = str(row[0])

    context = {
        "active_tab": "timeline",
        "week_start": week_start,
        "week_end": week_end,
        "chart_json": chart_json,
        "neg_pred": neg_pred,
        # ✅ 행동추천은 추후 붙일 거니까 지금은 빈 문자열로 고정
        "llm_ment": llm_ment,
    }
    return render(request, "timeline.html", context)
