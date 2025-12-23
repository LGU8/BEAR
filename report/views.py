from django.shortcuts import render
from datetime import date, datetime, timedelta, time
from django.db import connection, transaction
from django.http import HttpResponseBadRequest
import json

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

def get_week_range(target_date):
    # target_date가 포함된 주의 월요일 ~ 일요일을 반환
    weekday = target_date.weekday() # 월=0, 일=6
    week_start = target_date - timedelta(days=weekday)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end

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
                print(nut_data)

                sql = """
                SELECT mood, energy
                FROM CUS_FEEL_TH
                WHERE cust_id = %s
                AND rgs_dt = %s; 
                """

                cursor.execute(sql, [cust_id, rgs_dt])
                feel_daily = cursor.fetchall()

                mood = []
                for feel in feel_daily:
                    mood.append(feel[0])

                pos = (mood.count('pos')/len(mood))
                neu = (mood.count('neu')/len(mood))
                neg = (mood.count('neg')/len(mood))

    except Exception as e:
        return HttpResponseBadRequest(f"SELECT 오류 발생: {e}")

    context = {"selected_date": selected_date.strftime("%Y-%m-%d"),
               "active_tab": "report",
               "nut_day": json.dumps(nut_data),
               "mood_ratio": json.dumps({'pos': pos, "neu": neu, "neg": neg}),
               }
    print(context)

    return render(request, "report/report_daily.html", context)

def report_weekly(request):
    selected_date = get_selected_date(request)
    week_start, week_end = get_week_range(selected_date)
    context = {"week_start": week_start.strftime("%Y-%m-%d"),
               "week_end": week_end.strftime("%Y-%m-%d"),
               "active_tab": "report",}
    return render(request, "report/report_weekly.html", context)