# from django.shortcuts import render
# from datetime import date, datetime, timedelta
# from django.db import connection
# import json
#
#
# from record.services.timeline_ml_predict import predict_negative_risk
#
#
# from django.contrib.auth.decorators import login_required
# from django.shortcuts import render
#
# @login_required(login_url='/') # 비로그인 시 루트(/) 즉, 로그인 페이지로 이동
# def index(request):
#     # index.html 없이 바로 껍데기(base.html)만 보여줍니다.
#     return render(request, "base.html")
#
# @login_required(login_url='/')
# def badges(request):
#     return render(request, "badges.html")
#
#
#
# @login_required(login_url='/')
# def report_daily(request):
#     date_str = request.GET.get("date")
#
#     if date_str:
#         try:
#             selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
#         except ValueError:
#             selected_date = date.today()
#     else:
#         selected_date = date.today()
#
#     context = {
#         "selected_date": selected_date.strftime("%Y-%m-%d"),
#     }
#
#     return render(request, "report_daily.html", context)


from django.shortcuts import render, redirect
from datetime import date, datetime
from django.contrib.auth.decorators import login_required


# index 뷰: 로그인 후 첫 화면
@login_required(login_url="/")
def index(request):
    # base.html을 직접 렌더링하면 본문이 비어 보일 수 있으니,
    # 나중에 index.html을 만들어 상속받는 것을 추천합니다.
    return render(request, "home.html")


# badges 뷰
@login_required(login_url="/")
def badges(request):
    return render(
        request, "badges.html"
    )  # 파일명이 badge.html인지 badges.html인지 확인!


# report_daily 뷰
@login_required(login_url="/")
def report_daily(request):
    date_str = request.GET.get("date")

    if date_str:
        try:
            # 문자열을 날짜 객체로 변환
            selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            # 잘못된 날짜 형식이 들어오면 오늘 날짜로 대체
            selected_date = date.today()
    else:
        selected_date = date.today()

    context = {
        "selected_date": selected_date.strftime("%Y-%m-%d"),
        "user_email": request.user.email,  # 간단하게 사용자 정보도 넘겨봅니다.
    }

    return render(request, "report_daily.html", context)
