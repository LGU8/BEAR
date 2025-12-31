# conf/urls.py
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect  # ✅ 추가
from conf import views as conf_views
from record.views import timeline

def root_to_home(request):
    # ✅ accounts/login을 완전히 우회하고 home으로 보냄
    return redirect("home")

urlpatterns = [
    path("admin/", admin.site.urls),

    # ✅ 루트 주소 접속 시 home으로 우회
    path("", root_to_home, name="root"),

    # ✅ 로그인 후 이동할 홈 (지금은 "임시로 public" 처리할 예정)
    path("home/", conf_views.index, name="home"),

    # 앱 단위 include
    # ✅ accounts 자체가 지금 문제면, 일단 아래 1줄은 '임시로 주석' 가능
    # path("accounts/", include(("accounts.urls", "accounts_app"), namespace="accounts_app")),
    path("accounts/", include(("accounts.urls", "accounts_app"), namespace="accounts_app")),

    path("record/", include("record.urls")),
    path("settings/", include("settings.urls")),

    # 뷰 함수 직접 연결
    path("timeline/", timeline, name="timeline"),
    path("badges/", conf_views.badges_redirect, name="badges"),
    path("report/", include("report.urls")),
]

# menu_reco api root
try:
    urlpatterns += [
        path("api/", include("api.urls")),
    ]
except Exception:
    pass
