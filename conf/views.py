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
from django.utils import timezone
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Count

from record.models import CusFeelTh
from record.models import ReportTh
from record.views import build_today_food_payload 


def _safe_get_cust_id(request) -> str:
    """
    ✅ 로그인 구현을 건드리지 않고,
    '현재 로그인 사용자'에서 cust_id로 쓸 수 있는 후보를 안전하게 찾는다.

    우선순위:
    1) 세션에 cust_id가 있으면 그걸 최우선 (가장 안전)
    2) request.user.username
    3) request.user.email
    4) request.user에 cust_id 속성이 직접 있는 경우
    """
    # 1) session
    cust_id = request.session.get("cust_id")
    if cust_id:
        return str(cust_id)

    # 2) username
    if request.user.is_authenticated and getattr(request.user, "username", None):
        return str(request.user.username)

    # 3) email
    if request.user.is_authenticated and getattr(request.user, "email", None):
        return str(request.user.email)

    # 4) 혹시 user에 cust_id 필드가 있는 커스텀 User 모델인 경우
    if request.user.is_authenticated and getattr(request.user, "cust_id", None):
        return str(request.user.cust_id)

    return ""

def _build_daily_report_chart(cust_id: str, today_ymd: str) -> dict:
    """
    Home - 일일 리포트 섹션용 데이터 빌더.
    조건: type='D' AND rgs_dt=today_ymd AND cust_id=cust_id
    다건이면 updated_time 최신 1건.
    """
    if not cust_id:
        return {"rgs_dt": today_ymd, "content": ""}

    row = (
        ReportTh.objects
        .filter(cust_id=cust_id, type="D", rgs_dt=today_ymd)
        .order_by("-updated_time")
        .first()
    )

    if not row or not getattr(row, "content", None):
        return {"rgs_dt": today_ymd, "content": ""}

    return {"rgs_dt": row.rgs_dt, "content": row.content}



def _build_today_donut(cust_id: str, yyyymmdd: str):
    """
    CUS_FEEL_TH에서 오늘(cust_id, rgs_dt)의 mood를 집계해서
    donut dict를 만들고, 데이터 없으면 None 반환.
    """
    if not cust_id:
        return None

    qs = (
        CusFeelTh.objects
        .filter(cust_id=cust_id, rgs_dt=yyyymmdd)
        .values("mood")
        .annotate(cnt=Count("mood"))
    )

    counts = {"pos": 0, "neu": 0, "neg": 0}
    for row in qs:
        m = row.get("mood")
        if m in counts:
            counts[m] = int(row.get("cnt", 0))

    pos_count = counts["pos"]
    rest_count = counts["neu"] + counts["neg"]
    total = pos_count + rest_count

    if total <= 0:
        return None

    pos_pct = round((pos_count / total) * 100)

    return {
        "rgs_dt": yyyymmdd,
        "pos_count": pos_count,
        "rest_count": rest_count,
        "total": total,
        "pos_pct": pos_pct,
    }


# index 뷰: 로그인 후 첫 화면
@login_required(login_url="/")
def index(request):
    # ✅ 기존 구조 유지: home.html 렌더는 그대로, 단 context만 추가

    today_str = datetime.now().strftime("%Y%m%d")
    cust_id = _safe_get_cust_id(request)
    today_ymd = timezone.localdate().strftime("%Y%m%d")

    donut = _build_today_donut(cust_id=cust_id, yyyymmdd=today_str)
    daily_report = _build_daily_report_chart(cust_id, today_ymd)
    food_payload = build_today_food_payload(cust_id=cust_id, today_ymd=today_ymd)

    context = {
    "menu_reco": None,
    "today_ymd": today_ymd,
    "daily_report": daily_report,

    # ✅ 템플릿과 JS가 읽을 키
    "food_payload_json": json.dumps(food_payload, ensure_ascii=False),

    # (선택) 기존 키 유지하고 싶으면 같이 둬도 됨
    "today_meals": json.dumps(food_payload, ensure_ascii=False),

    "donut": donut,
}




    return render(request, "home.html", context)


# badges 뷰
@login_required(login_url="/")
def badges(request):
    return render(request, "badges.html")




# # report_daily 뷰
# @login_required(login_url="/")
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
#         "user_email": request.user.email,
#     }
#
#     return render(request, "report_daily.html", context)