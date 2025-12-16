from django.urls import path, include
from conf.views import index
from record import views

app_name = "record_app"

urlpatterns = [
    path("", views.record_index, name="record_index"),
    path("recipes/", views.recipe_search, name="recipe_search"),
    path("recipes/new/", views.recipe_new, name="recipe_new"),
    path("camera/", views.camera, name="camera"),
    path("scan/result/", views.scan_result, name="scan_result"),
    # OCR/Barcode 처리 API
    path("api/scan/", views.api_scan, name="api_scan"),
]
