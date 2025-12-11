from django.urls import path,include
from conf.views import index
from settings import views

app_name = "settings_app"

urlpatterns = [
    path('',views.settings_index, name="settings_index"),

]
