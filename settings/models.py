# settings/models.py
from django.db import models


class CustTM(models.Model):
    cust_id = models.CharField(max_length=10, primary_key=True)
    email = models.CharField(max_length=255, unique=True)
    password = models.CharField(max_length=1000)

    created_dt = models.CharField(max_length=8, null=True, blank=True)
    last_login_dt = models.CharField(max_length=14, null=True, blank=True)
    updated_dt = models.CharField(max_length=8, null=True, blank=True)
    leave_dt = models.CharField(max_length=14, null=True, blank=True)

    retry_cnt = models.IntegerField(default=0)
    lock_yn = models.CharField(max_length=1, default="N")

    nickname = models.CharField(max_length=50, null=True, blank=True)

    created_time = models.CharField(max_length=14, null=True, blank=True)
    updated_time = models.CharField(max_length=14, null=True, blank=True)

    class Meta:
        db_table = "CUST_TM"
        managed = False


class CusProfileTS(models.Model):
    cust_id = models.CharField(max_length=10, primary_key=True)

    height_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    bmi = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    bmr = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    gender = models.CharField(max_length=1, null=True, blank=True)
    birth_dt = models.CharField(max_length=8, null=True, blank=True)

    Ratio_carb = models.IntegerField(null=True, blank=True)
    Ratio_protein = models.IntegerField(null=True, blank=True)
    Ratio_fat = models.IntegerField(null=True, blank=True)

    activity_level = models.CharField(max_length=1, null=True, blank=True)
    purpose = models.CharField(max_length=1, null=True, blank=True)

    Calories_burned = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    Recommended_calories = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    Offset = models.FloatField(null=True, blank=True)

    created_time = models.CharField(max_length=14, null=True, blank=True)
    updated_time = models.CharField(max_length=14, null=True, blank=True)

    class Meta:
        db_table = "CUS_PROFILE_TS"
        managed = False
