from django.http import HttpResponseBadRequest
from django.shortcuts import render, redirect
from datetime import datetime, timedelta
from django.db import connection, transaction
from django.utils import timezone
import json
import traceback

from conf.views import _safe_get_cust_id
from django.views.decorators.csrf import ensure_csrf_cookie


# =========================
# record_mood
# =========================
def record_mood(request):
    # ✅ report.views가 LLM import를 당길 수 있으니 lazy import + fallback
    try:
        from report.views import get_selected_date

        selected_date = get_selected_date(request)
    except Exception:
        selected_date = timezone.localdate()

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

    except Exception as e:
        return HttpResponseBadRequest(f"저장 중 오류 발생: {e}")
    from ml.lstm.event_hooks import on_mood_recorded

    transaction.on_commit(
        lambda: on_mood_recorded(
            cust_id=cust_id, rgs_dt=rgs_dt, time_slot=time_slot, seq=int(seq)
        )
    )

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


@ensure_csrf_cookie
def camera(request):
    return render(request, "record/camera.html")


def scan_result(request):
    return render(request, "record/scan_result.html")


# =========================
# timeline helpers
# =========================
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
    s = (source_slot or "").upper()
    if s == "M":
        return (source_date_ymd, "L")
    if s == "L":
        return (source_date_ymd, "D")

    d = datetime.strptime(source_date_ymd, "%Y%m%d").date()
    next_ymd = (d + timedelta(days=1)).strftime("%Y%m%d")
    return (next_ymd, "M")


# =========================
# timeline
# =========================
def timeline(request):
    """
    감정 변화 요약 (주간)
    + (중요) 서버에서는 무거운 ML/RAG를 절대 여기서 돌리지 않는다.
    - timeline은 "조회 전용(read-only)"으로 유지한다.
    """

    cust_id = _safe_get_cust_id(request)

    # ---- ENTER LOG ----
    print(
        "[TLDBG][ENTER]",
        "path=",
        request.path,
        "method=",
        request.method,
        "session_key=",
        getattr(request.session, "session_key", None),
        "_auth_user_id=",
        request.session.get("_auth_user_id"),
        "session_cust_id=",
        request.session.get("cust_id"),
        "user_auth=",
        request.user.is_authenticated,
        "user_cust_id=",
        getattr(request.user, "cust_id", None),
        "cust_id_var=",
        cust_id,
        flush=True,
    )

    # 1) 기간 파라미터
    start = request.GET.get("start")
    end = request.GET.get("end")

    today = timezone.localdate()

    # ✅ 먼저 end_date/start_date를 "정의"한 뒤에만 로그 찍기
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

    print(
        "[TLDBG][DATE]",
        "today=",
        today.strftime("%Y-%m-%d"),
        "start=",
        start,
        "end=",
        end,
        "start_date=",
        start_date.strftime("%Y-%m-%d"),
        "end_date=",
        end_date.strftime("%Y-%m-%d"),
        flush=True,
    )

    week_start = start_date.strftime("%Y.%m.%d")
    week_end = end_date.strftime("%Y.%m.%d")

    # 2) 주간 누적막대 SQL
    sql_week = """
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
        cursor.execute(sql_week, [cust_id, start, end])
        rows = cursor.fetchall()

    day_to_score = {}
    for rgs_dt, pos_s, neu_s, neg_s in rows:
        day_to_score[str(rgs_dt)] = (
            int(pos_s or 0),
            int(neu_s or 0),
            int(neg_s or 0),
        )

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
        {"labels": labels, "pos": pos, "neu": neu, "neg": neg, "y_max": 9},
        ensure_ascii=False,
    )

    # =========================
    # (2) 부정 감정 예측 표시: "DB 조회만"
    # =========================
    source_date = _pick_source_date_today_or_yesterday(cust_id)
    today_ymd = timezone.localdate().strftime("%Y%m%d")
    yest_ymd = (timezone.localdate() - timedelta(days=1)).strftime("%Y%m%d")

    target_date, target_slot = None, None
    neg_pred = {
        "eligible": False,
        "reason": "데이터가 없습니다",
        "detail": {
            "type": "no_recent_record",
            "asof": today_ymd,
            "missing_days": [yest_ymd, today_ymd],
        },
        "missing_days": [yest_ymd, today_ymd],
    }

    print(
        "[TLDBG][SOURCE]",
        "cust_id=",
        cust_id,
        "source_date=",
        source_date,
        flush=True,
    )

    if source_date is not None:
        source_slot = _pick_source_slot_DLM(cust_id, source_date)

        print(
            "[TLDBG][SOURCE_SLOT]",
            "cust_id=",
            cust_id,
            "source_date=",
            source_date,
            "source_slot=",
            source_slot,
            flush=True,
        )

        if source_slot is not None:
            target_date, target_slot = _target_from_source(source_date, source_slot)

            # ✅ 여기서부터는 DB 조회만 한다 (절대 ML 호출 X)
            sql_risk = """
                SELECT risk_score, risk_level, updated_time
                FROM CUS_FEEL_RISK_TH
                WHERE cust_id = %s
                  AND target_date = %s
                  AND target_slot = %s
                LIMIT 1
            """
            with connection.cursor() as cursor:
                cursor.execute(sql_risk, [cust_id, target_date, target_slot])
                r = cursor.fetchone()

            if r:
                risk_score, risk_level, updated_time = r
                # risk_score(0~100) -> p_highrisk(0~1)로 환산
                try:
                    p_high = float(risk_score or 0) / 100.0
                except Exception:
                    p_high = 0.0

                neg_pred = {
                    "eligible": True,
                    "reason": "DB 조회 결과",
                    "p_highrisk": p_high,
                    "risk_score": int(risk_score or 0),
                    "risk_level": str(risk_level or ""),
                    "detail": {
                        "type": "from_db",
                        "asof": source_date,
                        "target_date": target_date,
                        "target_slot": target_slot,
                        "updated_time": (
                            str(updated_time) if updated_time is not None else None
                        ),
                        "missing_days": [],
                    },
                    "missing_days": [],
                }
            else:
                # source는 있는데 target 예측이 DB에 아직 없음
                neg_pred = {
                    "eligible": False,
                    "reason": "예측 결과가 아직 생성되지 않았습니다",
                    "detail": {
                        "type": "no_pred_row",
                        "rule": "예측/추천은 record 저장 시점에서 생성되어야 합니다",
                        "asof": source_date,
                        "target_date": target_date,
                        "target_slot": target_slot,
                        "missing_days": [],
                    },
                    "missing_days": [],
                }

            print(
                "[TLDBG][RISK_ROW]",
                "cust_id=",
                cust_id,
                "target_date=",
                target_date,
                "target_slot=",
                target_slot,
                "eligible=",
                neg_pred.get("eligible"),
                "reason=",
                neg_pred.get("reason"),
                "detail_type=",
                (neg_pred.get("detail") or {}).get("type"),
                flush=True,
            )

    # =========================
    # (추가) UI용 상태 계산
    # =========================
    neg_pred["ui_active_idx"] = 1
    neg_pred["ui_status_text"] = "예측 준비 중"

    if not neg_pred.get("eligible", False):
        dtype = (neg_pred.get("detail") or {}).get("type")
        if dtype == "no_recent_record":
            neg_pred["ui_active_idx"] = 1
            neg_pred["ui_status_text"] = "데이터 없음"
        elif dtype == "no_pred_row":
            neg_pred["ui_active_idx"] = 1
            neg_pred["ui_status_text"] = "예측 없음"
        else:
            neg_pred["ui_active_idx"] = 1
            neg_pred["ui_status_text"] = "예측 준비 중"
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

    # =========================
    # (추가) 행동추천 멘트 조회: DB 조회만
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

    print(
        "[TLDBG][EXIT]",
        "cust_id=",
        cust_id,
        "target_date=",
        target_date,
        "target_slot=",
        target_slot,
        "llm_ment_len=",
        len(llm_ment or ""),
        flush=True,
    )

    context = {
        "active_tab": "timeline",
        "week_start": week_start,
        "week_end": week_end,
        "chart_json": chart_json,
        "neg_pred": neg_pred,
        "llm_ment": llm_ment,
    }
    return render(request, "timeline.html", context)
