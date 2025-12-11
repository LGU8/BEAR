from django.shortcuts import render

# Create your views here.
def record_index(request):
    return render(request, "record_index.html")