from django.shortcuts import render

# Create your views here.
def settings_index(request):
    return render(request, "settings/settings_index.html")