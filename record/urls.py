from django.urls import path,include
from conf.views import index
from record import views

app_name = "record_app"

urlpatterns = [
    path('',views.record_index, name="record_index"),

]
