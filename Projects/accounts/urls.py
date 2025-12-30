from django.urls import path
from . import views

app_name = "accounts_app"

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.user_login, name="user_login"),
    path("logout/", views.user_logout, name="user_logout"),

    # password reset (중복 제거, name 유지)
    path("password-reset/", views.password_reset, name="password_reset"),
    path("password-reset-confirm/<uidb64>/<token>/", views.password_reset_confirm, name="password_reset_confirm"),

    # signup (prefix 정리)
    path("signup_step1/", views.signup_step1, name="signup_step1"),
    path("signup_step2/", views.signup_step2, name="signup_step2"),
    path("signup_step3/", views.signup_step3, name="signup_step3"),
    path("signup_step4/", views.signup_step4, name="signup_step4"),

    path("profile/", views.profile, name="profile"),
    path("test-login/", views.test_login_view, name="test_login"),
]
