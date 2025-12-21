from django.shortcuts import render
from datetime import date, datetime, timedelta

def get_selected_date(request):
    date_str = request.GET.get("date")
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.today()

def get_week_range(target_date):
    # target_date가 포함된 주의 월요일 ~ 일요일을 반환
    weekday = target_date.weekday() # 월=0, 일=6
    week_start = target_date - timedelta(days=weekday)
    week_end = week_start + timedelta(days=6)
    print(week_start, week_end)
    return week_start, week_end

def report_daily(request):
    selected_date = get_selected_date(request)
    context = {"selected_date": selected_date.strftime("%Y-%m-%d")}
    return render(request, "report/report_daily.html", context)

def report_weekly(request):
    selected_date = get_selected_date(request)
    week_start, week_end = get_week_range(selected_date)
    context = {"week_start": week_start.strftime("%Y-%m-%d"),
               "week_end": week_end.strftime("%Y-%m-%d"),}
    return render(request, "report/report_weekly.html", context)