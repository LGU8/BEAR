from django.db import models
from django.contrib.auth.models import AbstractBaseUser
import datetime

class Cust(AbstractBaseUser):
    # SQL: CUST_TM
    cust_id = models.CharField(max_length=10, primary_key=True)
    email = models.CharField(max_length=254, unique=True)
    password = models.CharField(max_length=1000)
    created_dt = models.CharField(max_length=8, null=True, blank=True)
    last_login = models.CharField(max_length=8, null=True, blank=True, db_column='last_login_dt')
    updated_dt = models.CharField(max_length=8, null=True, blank=True)
    leave_dt = models.CharField(max_length=8, null=True, blank=True)
    retry_cnt = models.IntegerField(default=0, null=True, blank=True)
    lock_yn = models.CharField(max_length=1, default='N', null=True, blank=True)
    created_time = models.CharField(max_length=14, null=True, blank=True)
    updated_time = models.CharField(max_length=14, null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'CUST_TM'
        managed = False  # ⭐ Django가 테이블을 생성/삭제하지 않음

    def save(self, *args, **kwargs):
        # 8자리 날짜 형식 강제 (SQL 스키마 일치)
        if self.last_login and not isinstance(self.last_login, str):
            self.last_login = self.last_login.strftime('%Y%m%d')
        super().save(*args, **kwargs)

# ⭐ 이 모델이 누락되어 ImportError가 발생했던 것입니다. ⭐
class LoginHistory(models.Model):
    # SQL: LOGIN_TH
    cust = models.ForeignKey(Cust, on_delete=models.CASCADE, db_column='cust_id', primary_key=True)
    login_dt = models.CharField(max_length=8)
    seq = models.BigIntegerField()
    login_time = models.CharField(max_length=14, null=True, blank=True)
    logout_time = models.CharField(max_length=14, null=True, blank=True)
    success_yn = models.CharField(max_length=1, null=True, blank=True)
    created_time = models.CharField(max_length=14, null=True, blank=True)
    updated_time = models.CharField(max_length=14, null=True, blank=True)

    class Meta:
        db_table = 'LOGIN_TH'
        managed = False
        unique_together = (('cust', 'login_dt', 'seq'),)

class CusProfile(models.Model):
    # SQL: CUS_PROFILE_TS
    cust = models.OneToOneField(Cust, on_delete=models.CASCADE, primary_key=True, db_column='cust_id')
    height_cm = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    weight_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    bmi = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    bmr = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    gender = models.CharField(max_length=1, null=True)
    birth_dt = models.CharField(max_length=8, null=True)
    ratio_carb = models.IntegerField(db_column='Ratio_carb', null=True)
    ratio_protein = models.IntegerField(db_column='Ratio_protein', null=True)
    ratio_fat = models.IntegerField(db_column='Ratio_fat', null=True)
    activity_level = models.CharField(max_length=1, null=True)
    purpose = models.CharField(max_length=1, null=True)
    calories_burned = models.DecimalField(max_digits=7, decimal_places=2, db_column='Calories_burned', null=True)
    recommended_calories = models.DecimalField(max_digits=7, decimal_places=2, db_column='Recommended_calories', null=True)
    offset = models.FloatField(db_column='Offset', null=True)
    created_time = models.CharField(max_length=14, null=True)
    updated_time = models.CharField(max_length=14, null=True)

    class Meta:
        db_table = 'CUS_PROFILE_TS'
        managed = False