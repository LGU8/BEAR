from django.shortcuts import render


# Create your views here.
def record_index(request):
    return render(request, "record/record_index.html")


def recipe_search(request):
    return render(request, "record/recipe_search.html")


def recipe_new(request):
    return render(request, "record/recipe_new.html")


def camera(request):
    return render(request, "record/camera.html")


def scan_result(request):
    return render(request, "record/scan_result.html")


def api_scan(request):
    return render(request, "record/scan_result.html")
