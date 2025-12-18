from django.urls import path
from . import views
from conf.views import index

app_name = "accounts_app"

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.user_login, name="user_login"),
    # 2. 로그아웃 URL (views.user_logout 함수와 연결)
    path("logout/", views.user_logout, name="user_logout"),
    path("password-reset/", views.password_reset),
    path("signup_step1/", views.signup_step1, name="signup_step1"),
    path("accounts/signup_step2/", views.signup_step2, name="signup_step2"),
    path("signup_step3/", views.signup_step3, name="signup_step3"),
    path("signup_step4/", views.signup_step4, name="signup_step4"),
    # 3. 프로필 URL (views.profile 함수와 연결)
    path("profile/", views.profile, name="profile"),
    path('password-reset/', views.password_reset, name='password_reset'),
    path('test-login/', views.test_login_view, name='test_login'),
]
