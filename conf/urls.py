# """
# URL configuration for conf project.
#
# The `urlpatterns` list routes URLs to views. For more information please see:
#     https://docs.djangoproject.com/en/4.2/topics/http/urls/
# Examples:
# Function views
#     1. Add an import:  from my_app import views
#     2. Add a URL to urlpatterns:  path('', views.home, name='home')
# Class-based views
#     1. Add an import:  from other_app.views import Home
#     2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
# Including another URLconf
#     1. Import the include() function: from django.urls import include, path
#     2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
# """
#
# from django.contrib import admin
# from django.urls import path, include
# from django.conf import settings
# from django.conf.urls.static import static
# from conf.views import index, badges, report_daily
# from record.views import timeline
#
# urlpatterns = [
#     path("admin/", admin.site.urls),
#     path("", index),
#     path("accounts/",include("accounts.urls")),
#     path("record/", include("record.urls")),
#     path("settings/", include("settings.urls")),
#     path("timeline/", timeline),
#     path("badges/", badges),
#     path("report_daily/", include("report.urls")),
# ]


# conf/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from conf.views import index, badges, report_daily
from record.views import timeline
from accounts.views import user_login  # 로그인 뷰 직접 임포트

urlpatterns = [
    path("admin/", admin.site.urls),

    # 1. 루트 접속 시 바로 로그인 페이지가 뜨게 설정
    path("", user_login, name="root"),

    # 2. 로그인 후 실제 메인 화면(index)으로 보낼 경로
    path("home/", index, name="home"),

    path("accounts/", include("accounts.urls")),
    path("record/", include("record.urls")),
    path("settings/", include("settings.urls")),

    path("timeline/", timeline, name="timeline"),
    path("badges/", badges, name="badges"),

    # report_daily가 앱이라면 include 사용, 함수라면 path 사용
    # 현재 include("report.urls")로 되어 있으니 해당 앱의 urls.py를 따라갑니다.
    path("report_daily/", include("report.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)