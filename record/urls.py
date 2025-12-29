# record/urls.py
from django.urls import path
from . import views, views_api

app_name = "record_app"

urlpatterns = [
    path("", views.record_mood, name="record_mood"),
    path("meal/", views.record_meal, name="record_meal"),
    path("recipes/", views.recipe_search, name="recipe_search"),
    path("recipes/new/", views.recipe_new, name="recipe_new"),
    path("camera/", views.camera, name="camera"),
    path("scan/result/", views.scan_result, name="scan_result"),
    # OCR/Barcode 처리 API
    path("api/scan/barcode/", views_api.api_barcode_scan, name="api_barcode_scan"),
    path("api/scan/draft/", views_api.api_barcode_draft, name="api_barcode_draft"),
    path("api/scan/commit/", views_api.api_barcode_commit, name="api_barcode_commit"),
    path("api/foods/search/", views_api.api_food_search, name="api_food_search"),
    path("api/ocr/job/create/", views_api.api_ocr_job_create, name="api_ocr_job_create"),
    path("api/ocr/job/status/", views_api.api_ocr_job_status, name="api_ocr_job_status"),
    path("api/ocr/job/result/", views_api.api_ocr_job_result, name="api_ocr_job_result"),
    path("api/ocr/job/commit-manual/", views_api.api_ocr_commit_manual, name="api_ocr_commit_manual"),

    # record_mood - keyword 처리 API
    path("api/keywords/", views_api.keyword_api, name="keyword_api"),
    path("api/meals/add/", views_api.api_meal_add, name="api_meal_add"),
    path("api/meals/recent3/", views_api.api_meals_recent3, name="api_meals_recent3"),
    path("api/meal/save/", views_api.api_meal_save_by_search, name="api_meal_save_by_search"),
    path("api/scan/commit/", views_api.api_scan_commit, name="api_scan_commit"),
]
