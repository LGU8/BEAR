# accounts/urls.py (권장: 현재와 동일 + 가독성만 정리)

from django.urls import path
from . import views

app_name = "accounts_app"

urlpatterns = [
    path("login/", views.user_login, name="user_login"),
    path("logout/", views.user_logout, name="user_logout"),

    # password reset
    path("password-reset/", views.password_reset, name="password_reset"),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        views.password_reset_confirm,
        name="password_reset_confirm",
    ),

    # signup
    path("signup_step1/", views.signup_step1, name="signup_step1"),
    path("signup_step2/", views.signup_step2, name="signup_step2"),
    path("signup_step3/", views.signup_step3, name="signup_step3"),
    path("signup_step4/", views.signup_step4, name="signup_step4"),

    path("profile/", views.profile, name="profile"),
    path("demo/start/", views.demo_start_view, name="demo_start"),

    path("test-login/", views.test_login_view, name="test_login"),
]
