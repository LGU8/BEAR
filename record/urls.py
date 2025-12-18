from django.urls import path, include
from conf.views import index
from . import views, views_api

app_name = "record_app"

urlpatterns = [
    path("", views.record_index, name="record_index"),
    path("recipes/", views.recipe_search, name="recipe_search"),
    path("recipes/new/", views.recipe_new, name="recipe_new"),
    path("camera/", views.camera, name="camera"),
    path("scan/result/", views.scan_result, name="scan_result"),
    # OCR/Barcode 처리 API
    path("api/scan/barcode/", views_api.api_barcode_scan, name="api_barcode_scan"),
    path("api/scan/draft/", views_api.api_barcode_draft, name="api_barcode_draft"),
    path("api/scan/commit/", views_api.api_barcode_commit, name="api_barcode_commit"),
]
