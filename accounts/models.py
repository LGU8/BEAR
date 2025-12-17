# accounts/models.py
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

from django.utils import timezone
# 파이썬 표준 datetime 모듈의 datetime 객체를 명시적으로 임포트합니다.
import datetime

class Cust(AbstractBaseUser):
    # ========================================================
    # 1. Django 인증 시스템 필수 속성 (최소화)
    # ========================================================
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []


    # ========================================================
    # 2. DB 스키마 일치 및 필드 정의 (VARCHAR(10) 및 CHAR(8) 유지)
    # ========================================================

    # CUST_TM.cust_id (VARCHAR(10) PRIMARY KEY)
    cust_id = models.CharField(max_length=10, primary_key=True)

    # email과 password는 AbstractBaseUser가 처리합니다.
    email = models.CharField(max_length=255, unique=True)
    password = models.CharField(max_length=1000)

    # CUST_TM.last_login_dt (CHAR(8))를 Django의 last_login으로 오버라이드
    # AbstractBaseUser는 last_login 필드를 요구합니다.
    last_login = models.CharField(
        max_length=14,
        null=True,
        blank=True,
        db_column='last_login_dt'  # DB 컬럼 이름 지정
    )

    def save(self, *args, **kwargs):
        # last_login 필드가 업데이트되는지 확인
        if 'update_fields' in kwargs and 'last_login' in kwargs['update_fields']:
            # 현재 self.last_login은 Django가 할당한 datetime 객체입니다.
            if isinstance(self.last_login, timezone.datetime):
                # datetime 객체를 'YYYYMMDDHHMMSS' 형식의 문자열로 변환합니다.
                self.last_login = self.last_login.strftime('%Y%m%d%H%M%S')

        elif not kwargs:
            # 일반 save() 호출 시에도 last_login이 datetime 객체라면 변환합니다.
            if isinstance(self.last_login, timezone.datetime):
                self.last_login = self.last_login.strftime('%Y%m%d%H%M%S')

        super().save(*args, **kwargs)


    # 기타 필드
    created_dt = models.CharField(max_length=8)
    updated_dt = models.CharField(max_length=8, null=True, blank=True)
    leave_dt = models.CharField(max_length=8, null=True, blank=True)  # CHAR(8) 유지
    retry_cnt = models.IntegerField(default=0)
    lock_yn = models.CharField(max_length=1, default='N')




    class Meta:
        db_table = 'CUST_TM'

    def __str__(self):
        return self.email


class LoginHistory(models.Model):
    """
    LOGIN_TH
    """
    id = models.BigAutoField(primary_key=True)
    cust = models.ForeignKey(
        Cust,
        on_delete=models.CASCADE,
        db_column='cust_id'
    )
    login_dt = models.CharField(max_length=8)
    seq = models.BigIntegerField()
    login_time = models.CharField(max_length=14)
    logout_time = models.CharField(max_length=14, null=True, blank=True)
    success_yn = models.CharField(max_length=1)

    class Meta:
        db_table = 'login_th'
        unique_together = ('cust', 'login_dt', 'seq')

class CusProfile(models.Model):
    # FK 설정: cust_id는 VARCHAR(10)이므로 OneToOneField 사용
    cust = models.OneToOneField(Cust, on_delete=models.CASCADE, primary_key=True, db_column='cust_id')

    # 스키마에 따라 null=True 설정 (signup_step1 오류 방지)
    height_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    bmi = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    bmr = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True) # DECIMAL(6,2) 유지

    gender = models.CharField(max_length=1, null=True, blank=True)
    birth_dt = models.CharField(max_length=8, null=True, blank=True)

    ratio_carb = models.IntegerField(null=True, blank=True)
    ratio_protein = models.IntegerField(null=True, blank=True)
    ratio_fat = models.IntegerField(null=True, blank=True)

    activity_level = models.CharField(max_length=1, null=True, blank=True)
    purpose = models.CharField(max_length=1, null=True, blank=True)

    calories_burned = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    recommended_calories = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    offset = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = 'CUS_PROFILE_TS'