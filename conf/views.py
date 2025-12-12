from django.shortcuts import render


def index(request):
    return render(request, "index.html")


def timeline(request):
    return render(request, "index.html", {"active_tab": "timeline"})
