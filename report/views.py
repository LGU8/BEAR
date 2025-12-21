from django.shortcuts import render
from datetime import date, datetime

def get_selected_date(request):
    date_str = request.GET.get("date")
    if date_str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.today()

def report_daily(request):
    selected_date = get_selected_date(request)
    context = {"selected_date": selected_date.strftime("%Y-%m-%d")}
    return render(request, "report/report_daily.html", context)

def report_weekly(request):
    selected_date = get_selected_date(request)
    context = {"selected_date": selected_date.strftime("%Y-%m-%d")}
    return render(request, "report/report_weekly.html", context)