from django.shortcuts import render
from datetime import date, datetime, timedelta, time
from django.db import connection, transaction
from django.http import HttpResponseBadRequest
import json
from ml.report import report_daily_langchain
from ml.report.report_daily_langchain import make_daily_feedback


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

def daily_total_nutrition(nut_data):
    total_nut = {"kcal": 0, "carb": 0, "protein": 0, "fat": 0}

    for index, value in enumerate(nut_data.values()):
        if index > 0:
            total_nut["kcal"] += value["kcal"]
            total_nut["carb"] += value["carb"]
            total_nut["protein"] += value["protein"]
            total_nut["fat"] += value["fat"]

    return total_nut

def daily_keywords(keywords):
    keywords_daily = []
    for words in keywords:
        for w in words:
            keywords_daily.append(w)
    return keywords_daily

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
                # 권장 칼로리
                sql = """
                SELECT Recommended_calories, Ratio_carb, Ratio_protein, Ratio_fat FROM CUS_PROFILE_TS WHERE cust_id = %s
                """
                cursor.execute(sql, [cust_id])
                row = cursor.fetchone()
                recom_kcal = round(row[0])
                ratio_carb = round(row[1])
                ratio_pro = round(row[2])
                ratio_fat = round(row[3])

                recom_carb = round((recom_kcal*(ratio_carb/10))/4)
                recom_pro = round((recom_kcal*(ratio_pro/10))/4)
                recom_fat = round((recom_kcal*(ratio_fat/10))/9)

                # 영양소-요약
                sql = """
                SELECT time_slot, kcal, carb_g, protein_g, fat_g, 
                    (SELECT name FROM FOOD_TB b WHERE b.food_id = s.food_id) AS Name
                FROM CUS_FOOD_TH h
                JOIN (SELECT * FROM CUS_FOOD_TS) s
                on h.cust_id = s.cust_id AND h.rgs_dt = s.rgs_dt AND h.seq = s.seq
                WHERE h.cust_id = %s AND h.rgs_dt = %s; 
                """

                cursor.execute(sql, [cust_id, rgs_dt])
                nut_daily = cursor.fetchall()

                nut_data = {"recom": {"kcal": recom_kcal, "carb": recom_carb, "protein": recom_pro, "fat": recom_fat},
                            "M": {"kcal": 0, "carb": 0, "protein": 0, "fat": 0, "f_name": []},
                            "L": {"kcal": 0, "carb": 0, "protein": 0, "fat": 0, "f_name": []},
                            "D": {"kcal": 0, "carb": 0, "protein": 0, "fat": 0, "f_name": []}}

                for n in nut_daily:
                    for k in nut_data.keys():
                        if n[0] == k:
                            nut_data[k]['kcal'] = n[1]
                            nut_data[k]['carb'] = n[2]
                            nut_data[k]['protein'] = n[3]
                            nut_data[k]['fat'] = n[4]
                            nut_data[k]['f_name'].append(n[5])

                sql = """
                SELECT mood, energy
                FROM CUS_FEEL_TH
                WHERE cust_id = %s
                AND rgs_dt = %s; 
                """
                cursor.execute(sql, [cust_id, rgs_dt])
                feel_daily = cursor.fetchall()

                sql = """
                SELECT word
                FROM COM_FEEL_TM w
                JOIN (SELECT feel_id
                        FROM CUS_FEEL_TS
                        WHERE cust_id = %s
                        AND rgs_dt = %s) c
                ON w.feel_id = c.feel_id;
                """
                cursor.execute(sql, [cust_id, rgs_dt])
                keywords = cursor.fetchall()

                mood = []
                for feel in feel_daily:
                    mood.append(feel[0])

    except Exception as e:
        return HttpResponseBadRequest(f"SELECT 오류 발생: {e}")

    if not mood or not nut_daily:
        has_data = 0
        context = {"selected_date": selected_date.strftime("%Y-%m-%d"),
                   "active_tab": "report",
                   "has_data": has_data,}
    else:
        has_data = 1
        pos = (mood.count('pos') / len(mood))
        neu = (mood.count('neu') / len(mood))
        neg = (mood.count('neg') / len(mood))

        # feedback 용 데이터
        total_nut = daily_total_nutrition(nut_data)
        keywords_daily = daily_keywords(keywords)

        daily_data = {"cust_id": cust_id,
                      "date": selected_date.strftime("%Y-%m-%d"),
                      "positive_ratio": pos,
                      "neutral_ratio": neu,
                      "negative_ratio": neg,
                      "feeling_keywords": keywords_daily,
                      "total_kcal": total_nut['kcal'],
                      "total_carb": total_nut['carb'],
                      "total_protein": total_nut['protein'],
                      "total_fat": total_nut['fat'],
        }
        feedback = json.loads(make_daily_feedback(daily_data))

        context = {"selected_date": selected_date.strftime("%Y-%m-%d"),
                   "active_tab": "report",
                   "has_data": has_data,
                   "nut_day": json.dumps(nut_data),
                   "mood_ratio": json.dumps({'pos': pos, "neu": neu, "neg": neg}),
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