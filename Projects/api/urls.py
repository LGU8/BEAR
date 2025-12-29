# api/urls.py
from django.urls import path
from .views import menu_recommend_post, menu_recommend_get

urlpatterns = [
    path("menu/recommend", menu_recommend_post, name="menu_recommend_post"),  # POST
    path("menu/recommend/", menu_recommend_get, name="menu_recommend_get"),  # GET (끝 슬래시 허용)
]