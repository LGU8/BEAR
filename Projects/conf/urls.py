# conf/urls.py
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from conf import views as conf_views

def root_to_home(request):
    return redirect("home")

urlpatterns = [
    path("admin/", admin.site.urls),

    # 루트 주소 접속 시 home으로 우회
    path("", root_to_home, name="root"),

    # 로그인 후 이동할 홈
    path("home/", conf_views.index, name="home"),

    path("accounts/", include(("accounts.urls", "accounts_app"), namespace="accounts_app")),
    path("record/", include("record.urls")),
    path("settings/", include("settings.urls")),
    path("report/", include("report.urls")),

    # badges
    path("badges/", conf_views.badges_redirect, name="badges"),
]

# menu_reco api root
try:
    urlpatterns += [
        path("api/", include("api.urls")),
    ]
except Exception:
    pass
