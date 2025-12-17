from django.shortcuts import render
from datetime import date, datetime, timedelta
from django.db import connection
import json


from record.services.timeline_ml_predict import predict_negative_risk


def index(request):
    return render(request, "base.html")


def badges(request):
    return render(request, "badges.html")




def report_daily(request):
    date_str = request.GET.get("date")

    if date_str:
        try:
            selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            selected_date = date.today()
    else:
        selected_date = date.today()

    context = {
        "selected_date": selected_date.strftime("%Y-%m-%d"),
    }

    return render(request, "report_daily.html", context)
