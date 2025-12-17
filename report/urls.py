from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from report import views

app_name = "report_app"

urlpatterns = [
    path("", views.report_daily, name="report_daily"),
]
