from django.urls import path
from . import views

app_name = "settings_app"

urlpatterns = [
    path("", views.settings_index, name="settings_index"),                 # S0
    path("account/", views.settings_account, name="settings_account"),     # S1
    path("profile/edit/", views.settings_profile_edit, name="profile_edit"),   # S2
    path("preferences/edit/", views.settings_preferences_edit, name="preferences_edit"), # S3
    path("activity-goal/edit/", views.settings_activity_goal_edit, name="activity_goal_edit"), # S4
    path("password/", views.settings_password, name="settings_password"),    # S5
    path("badges/", views.settings_badges, name="settings_badges"),
]
