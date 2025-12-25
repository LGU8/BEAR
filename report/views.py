from django.shortcuts import render
from datetime import date, datetime, timedelta, time
from django.db import connection, transaction
from django.http import HttpResponseBadRequest
import json
from ml.report_llm.report_langchain import make_daily_feedback


def get_selected_date(request):
    date_str = request.GET.get("date")
    today = date.today()
    now = datetime.now()

    if date_str:
        try:
            selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            # 오늘이면 현재 시간 포함
            if selected_date == today:
                return now
            # 과거 날짜면 00:00:00
            return datetime.combine(selected_date, time.min)
        except ValueError:
            pass

    # date 파라미터가 없으면 → 오늘 + 현재 시간
    return now

def daily_feedback_input(id, date, nut_data, feeling_daily):
    daily_data = {"cust_id": id,
                  "date": date.strftime("%Y%m%d"),
                  "positive_ratio": float(feeling_daily[0][0]),
                  "neutral_ratio": float(feeling_daily[0][1]),
                  "negative_ratio": float(feeling_daily[0][2]),
                  "feeling_keywords": feeling_daily[0][3],
                  "kcal_needs": nut_data['recom'].get('kcal'),
                  "carb_needs": nut_data['recom'].get('carb'),
                  "protein_needs": nut_data['recom'].get('protein'),
                  "fat_needs": nut_data['recom'].get('fat'),
                  "kcal_intake": nut_data['total'].get('kcal'),
                  "carb_intake": nut_data['total'].get('carb'),
                  "protein_intake": nut_data['total'].get('protein'),
                  "fat_intake": nut_data['total'].get('fat'),
                  }
    feedback = json.loads(make_daily_feedback(daily_data))
    try:
        with connection.cursor() as cursor:
            today_time = datetime.now().strftime("%Y%m%d%H%M%S")
            sql = """
            INSERT INTO REPORT_TH (created_time, updated_time, cust_id, rgs_dt, type, period_start, period_end, content)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """

            data = [today_time, today_time, id, daily_data['date'], 'D', daily_data['date'], daily_data['date'], feedback['summary']]

            cursor.execute(sql, data)
    except Exception as e:
        return HttpResponseBadRequest(f"INSERT 오류 발생: {e}")
    return feedback['summary']

def check_generate_daily_report(selected_date, nut_data):
    today = date.today().strftime("%Y%m%d")
    selected_data = selected_date.strftime("%Y%m%d")
    if today == selected_data:
        dinner = nut_data.get("D", {})
        has_dinner_data = any(
            dinner.get(k, 0) > 0
            for k in ["kcal", "carb", "protein", "fat"]
        )

        # 2. 현재 시간이 저녁 8시 이후인지
        now = datetime.now().time()
        is_after_8pm = now >= time(20, 0)
        return has_dinner_data or is_after_8pm
    else:
        return 1

def get_last_week_range(target_date):
    # target_date기준 저번 주의 월요일 ~ 일요일을 반환
    weekday = target_date.weekday() # 월=0, 일=6
    week_start = target_date - timedelta(days=weekday+7)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end

def get_this_week_range(target_date):
    # target_date가 포함된 주의 월요일 ~ 일요일을 반환
    weekday = target_date.weekday() # 월=0, 일=6
    week_start = target_date - timedelta(days=weekday)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end

def check_3days_record(has_data_nut, has_data_mood):
    nut_stack, max_nut = 0, 0
    this_mood_stack, this_max_mood = 0, 0
    last_mood_stack, last_max_mood = 0, 0

    for ele in has_data_nut:
        if ele:
            nut_stack += 1
            max_nut = max(nut_stack, max_nut)
        else:
            nut_stack = 0

    for ele in has_data_mood[:7]:
        if ele:
            last_mood_stack += 1
            last_max_mood = max(last_mood_stack, last_max_mood)
        else:
            last_mood_stack = 0

    for ele in has_data_mood[7:]:
        if ele:
            this_mood_stack += 1
            this_max_mood = max(this_mood_stack, this_max_mood)
        else:
            this_mood_stack = 0

    over_3day_nut = max_nut >= 3
    over_3day_this_mood = this_max_mood >= 3
    over_3day_last_mood = last_max_mood >= 3

    return over_3day_nut, over_3day_this_mood, over_3day_last_mood

def report_daily(request):
    selected_date = get_selected_date(request)
    cust_id = request.user.cust_id
    rgs_dt = selected_date.strftime("%Y%m%d")

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # 영양소-요약
                sql = """
                SELECT Recommended_calories, 
                    round((Recommended_calories*(Ratio_carb/10))/4) AS Recom_carb, 
                    round((Recommended_calories*(Ratio_protein/10))/4) AS Recom_pro,
                    round((Recommended_calories*(Ratio_fat/10))/4) AS Recom_fat,
                    h.time_slot, h.kcal, h.carb_g, h.protein_g, h.fat_g, 
                    GROUP_CONCAT(name SEPARATOR ', ') AS NAME,
                    sum(kcal) OVER() AS total_kcal, sum(carb_g) OVER() AS total_carb, 
                   sum(protein_g) OVER() AS total_protein, sum(fat_g) OVER() AS total_fat
                FROM CUS_FOOD_TH h
                JOIN (SELECT * FROM CUS_PROFILE_TS) p
                ON h.cust_id = p.cust_id
                JOIN (SELECT * FROM CUS_FOOD_TS) s
                ON h.cust_id = s.cust_id AND h.rgs_dt = s.rgs_dt AND h.seq = s.seq
                JOIN (SELECT name, food_id FROM FOOD_TB) b
                ON s.food_id = b.food_id
                WHERE h.cust_id = %s AND h.rgs_dt = %s
                GROUP BY time_slot; 
                """

                cursor.execute(sql, [cust_id, rgs_dt])
                nut_daily = cursor.fetchall()

                # 감정 요약
                sql = """
                SELECT SUM(CASE WHEN c.mood = 'pos' THEN 1 ELSE 0 END)/COUNT(*) AS pos_ratio,
                       SUM(CASE WHEN c.mood = 'neu' THEN 1 ELSE 0 END)/COUNT(*) AS neu_ratio,
                       SUM(CASE WHEN c.mood = 'neg' THEN 1 ELSE 0 END)/COUNT(*) AS neg_ratio,
                       (SELECT GROUP_CONCAT(word SEPARATOR ', ') FROM COM_FEEL_TM w
                        JOIN (SELECT feel_id
                              FROM CUS_FEEL_TS
                              WHERE cust_id = %s
                              AND rgs_dt = %s) c
                        ON w.feel_id = c.feel_id) AS keywords,
                        (SELECT content FROM REPORT_TH 
                         WHERE cust_id = %s AND rgs_dt = %s AND type = 'D') AS feedback
                FROM CUS_FEEL_TH c
                WHERE cust_id = %s AND rgs_dt = %s; 
                """
                cursor.execute(sql, [cust_id, rgs_dt]*3)
                feeling_daily = cursor.fetchall()

    except Exception as e:
        return HttpResponseBadRequest(f"SELECT 오류 발생: {e}")

    if not feeling_daily or not nut_daily:
        has_data = 0
        context = {"selected_date": selected_date.strftime("%Y-%m-%d"),
                   "active_tab": "report",
                   "has_data": has_data,}
    else:
        has_data = 1

        # 영양소
        nut_data = {"recom": {"kcal": int(nut_daily[0][0]), "carb": int(nut_daily[0][1]),
                              "protein": int(nut_daily[0][2]), "fat": int(nut_daily[0][3])},
                    "M": {"kcal": 0, "carb": 0, "protein": 0, "fat": 0, "f_name": ""},
                    "L": {"kcal": 0, "carb": 0, "protein": 0, "fat": 0, "f_name": ""},
                    "D": {"kcal": 0, "carb": 0, "protein": 0, "fat": 0, "f_name": ""},
                    "total": {"kcal": int(nut_daily[0][10]), "carb": int(nut_daily[0][11]),
                              "protein": int(nut_daily[0][12]), "fat": int(nut_daily[0][13])}}

        for n in nut_daily:
            for k in nut_data.keys():
                if n[4] == k:
                    nut_data[k]['kcal'] = n[5]
                    nut_data[k]['carb'] = n[6]
                    nut_data[k]['protein'] = n[7]
                    nut_data[k]['fat'] = n[8]
                    nut_data[k]['f_name'] = n[9]

        can_report = check_generate_daily_report(selected_date, nut_data)

        if not can_report:
            context = {"selected_date": selected_date.strftime("%Y-%m-%d"),
                       "active_tab": "report",
                       "has_data": has_data,
                       "can_report": can_report}

        else:
            # 감정
            feel_data = {"pos": float(feeling_daily[0][0]),
                         "neu": float(feeling_daily[0][1]),
                         "neg": float(feeling_daily[0][2])}

            if feeling_daily[0][4]:
                feedback = feeling_daily[0][4]
            else:
                feedback = daily_feedback_input(cust_id, selected_date, nut_data, feeling_daily)

            context = {"selected_date": selected_date.strftime("%Y-%m-%d"),
                       "active_tab": "report",
                       "has_data": has_data,
                       "can_report": can_report,
                       "nut_day": json.dumps(nut_data, ensure_ascii=False),
                       "mood_day": json.dumps(feel_data),
                       "feedback": feedback,
                       }

    return render(request, "report/report_daily.html", context)

def report_weekly(request):
    selected_date = request.GET.get("date")
    cust_id = request.user.cust_id

    # report 날짜 결정
    if selected_date:
        target_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
        week_start, week_end = get_this_week_range(target_date)
        mood_start, dummy = get_last_week_range(target_date)
    else:
        today = date.today()
        week_start, week_end = get_last_week_range(today)
        mood_start, dummy = get_last_week_range(week_start)

    week_start_ymd = week_start.strftime("%Y%m%d")
    week_end_ymd = week_end.strftime("%Y%m%d")
    mood_start_ymd = mood_start.strftime("%Y%m%d")

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # 영양소-요약
                sql = """
                SELECT rgs_dt, kcal, carb_g, protein_g, fat_g
                FROM CUS_FOOD_TH
                WHERE rgs_dt BETWEEN %s AND %s
                AND cust_id = %s;
                """

                cursor.execute(sql, [week_start_ymd, week_end_ymd, cust_id])
                nut_weekly = cursor.fetchall()

                nut_data_week = {}
                has_data_nut = []
                for i in range(7):
                    day = (week_start + timedelta(days=i)).strftime("%Y%m%d")
                    nut_data_week[day] = {"kcal": 0, "carb": 0, "protein": 0, "fat": 0}
                    for n in nut_weekly:
                        if n[0] == day:
                            nut_data_week[day]["kcal"] += n[1]
                            nut_data_week[day]["carb"] += n[2]
                            nut_data_week[day]["protein"] += n[3]
                            nut_data_week[day]["fat"] += n[4]
                    if nut_data_week[day]["kcal"] != 0:
                        has_data_nut.append(True)
                    else:
                        has_data_nut.append(False)

                # 기분
                sql = """
                SELECT rgs_dt, mood
                FROM CUS_FEEL_TH
                WHERE rgs_dt BETWEEN %s AND %s
                AND cust_id = %s;
                """

                cursor.execute(sql, [mood_start_ymd, week_end_ymd, cust_id])
                mood_week_all = cursor.fetchall()

                mood_data_week = {}
                has_data_mood = []
                for i in range(14):
                    day = (mood_start + timedelta(days=i)).strftime("%Y%m%d")
                    mood_data_week[day] = []
                    for n in mood_week_all:
                        if n[0] == day:
                            mood_data_week[day].append(n[1])
                    if mood_data_week[day]:
                        has_data_mood.append(True)
                    else:
                        has_data_mood.append(False)
    except Exception as e:
        return HttpResponseBadRequest(f"SELECT 오류 발생: {e}")

    # 연속 3일 기록 여부 확인
    over_3day_nut, over_3day_this_mood, over_3day_last_mood = check_3days_record(has_data_nut, has_data_mood)

    if over_3day_nut and over_3day_this_mood:
        has_data = 1
        mood_ratio_week = {}
        for k, i in mood_data_week.items():
            mood_ratio_week[k] = {'pos': 0, 'neu': 0, 'neg': 0}
            if i:
                mood_ratio_week[k]['pos'] = (i.count('pos') / len(i))
                mood_ratio_week[k]['neu'] = (i.count('neu') / len(i))
                mood_ratio_week[k]['neg'] = (i.count('neg') / len(i))

        context = {"week_start": week_start.strftime("%Y-%m-%d"),
                   "week_end": week_end.strftime("%Y-%m-%d"),
                   "active_tab": "report",
                   "has_data": has_data,
                   "over_3day_nut":over_3day_nut,
                   "over_3day_this_mood": over_3day_this_mood,
                   "over_3day_last_mood":over_3day_last_mood,
                   "nut_data_week": json.dumps(nut_data_week),
                   "mood_ratio_week": json.dumps(mood_ratio_week)}

    else:
        has_data = 0
        context = {"week_start": week_start.strftime("%Y-%m-%d"),
                   "week_end": week_end.strftime("%Y-%m-%d"),
                   "active_tab": "report",
                   "has_data": has_data,
                   }

    return render(request, "report/report_weekly.html", context)