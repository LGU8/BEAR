# record/urls.py
from django.urls import path

app_name = "record_app"


def _v(name: str):
    def _proxy(request, *args, **kwargs):
        from record import views

        return getattr(views, name)(request, *args, **kwargs)

    return _proxy


def _a(name: str):
    def _proxy(request, *args, **kwargs):
        from record import views_api

        return getattr(views_api, name)(request, *args, **kwargs)

    return _proxy

def _k(name: str):
    def _proxy(request, *args, **kwargs):
        from record import views_keywords
        return getattr(views_keywords, name)(request, *args, **kwargs)
    return _proxy


urlpatterns = [
    path("", _v("record_mood"), name="record_mood"),
    path("meal/", _v("record_meal"), name="record_meal"),
    path("recipes/", _v("recipe_search"), name="recipe_search"),
    path("recipes/new/", _v("recipe_new"), name="recipe_new"),
    path("camera/", _v("camera"), name="camera"),
    path("scan/result/", _v("scan_result"), name="scan_result"),
    path("timeline/", _v("timeline"), name="timeline"),
    path("api/scan/barcode/", _a("api_barcode_scan"), name="api_barcode_scan"),
    path("api/scan/draft/", _a("api_barcode_draft"), name="api_barcode_draft"),
    path("api/scan/commit/", _a("api_barcode_commit"), name="api_barcode_commit"),
    path("api/foods/search/", _a("api_food_search"), name="api_food_search"),
    path("api/keywords/", _k("keyword_api"), name="keyword_api"),
    
    path("api/meals/add/", _a("api_meal_add"), name="api_meal_add"),
    path("api/meals/recent3/", _a("api_meals_recent3"), name="api_meals_recent3"),
    path(
        "api/meal/save/", _a("api_meal_save_by_search"), name="api_meal_save_by_search"
    ),
    path("api/ocr/job/create/", _a("api_ocr_job_create"), name="api_ocr_job_create"),
    path("api/ocr/job/status/", _a("api_ocr_job_status"), name="api_ocr_job_status"),
    path("api/ocr/job/result/", _a("api_ocr_job_result"), name="api_ocr_job_result"),
    path(
        "api/ocr/job/commit-manual/",
        _a("api_ocr_commit_manual"),
        name="api_ocr_commit_manual",
    ),
]
