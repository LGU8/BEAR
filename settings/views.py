from django.shortcuts import render

def settings_index(request):  # S0
    return render(request, "settings/settings_index.html")

def settings_account(request):  # S1
    return render(request, "settings/settings_account.html")

def settings_profile_edit(request):  # S2
    return render(request, "settings/settings_profile_edit.html")

def settings_preferences_edit(request):  # S3
    return render(request, "settings/settings_preferences_edit.html")

def settings_activity_goal_edit(request):  # S4
    return render(request, "settings/settings_activity_goal_edit.html")

def settings_password(request):  # S5
    return render(request, "settings/settings_password.html")
