# conf/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from conf import views as conf_views  # 이름을 구분해서 임포트
from record.views import timeline
from accounts.views import user_login

urlpatterns = [
    path("admin/", admin.site.urls),
    # 루트 주소 접속 시 로그인 페이지
    path("", user_login, name="root"),
    # 로그인 후 이동할 홈
    path("home/", conf_views.index, name="home"),
    # 앱 단위 include
    path("accounts/", include("accounts.urls")),
    path("record/", include("record.urls")),
    path("settings/", include("settings.urls")),
    # 뷰 함수 직접 연결 (데코레이터가 붙은 conf_views의 함수인지 확인!)
    path("timeline/", timeline, name="timeline"),
    path("badges/", conf_views.badges_redirect, name="badges"),
    # report가 include 방식이라면, 해당 앱의 views.py에도 @login_required가 있어야 합니다.
    path("report/", include("report.urls")),
]
# menu_reco api root
try:
    urlpatterns += [
        path("api/", include("api.urls")),
    ]
except Exception as e:
    # 부팅 우선: api는 잠시 비활성화
    pass
