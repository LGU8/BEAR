# from django.db import models
# from django.contrib.auth.models import AbstractBaseUser
# import datetime
#
# class Cust(AbstractBaseUser):
#     # SQL: CUST_TM
#     cust_id = models.CharField(max_length=10, primary_key=True)
#     email = models.CharField(max_length=254, unique=True)
#     password = models.CharField(max_length=1000)
#     created_dt = models.CharField(max_length=8, null=True, blank=True)
#     last_login = models.CharField(max_length=8, null=True, blank=True, db_column='last_login_dt')
#     updated_dt = models.CharField(max_length=8, null=True, blank=True)
#     leave_dt = models.CharField(max_length=8, null=True, blank=True)
#     retry_cnt = models.IntegerField(default=0, null=True, blank=True)
#     lock_yn = models.CharField(max_length=1, default='N', null=True, blank=True)
#     created_time = models.CharField(max_length=14, null=True, blank=True)
#     updated_time = models.CharField(max_length=14, null=True, blank=True)
#
#     USERNAME_FIELD = 'email'
#     REQUIRED_FIELDS = []
#
#     class Meta:
#         db_table = 'CUST_TM'
#         managed = False  # ⭐ Django가 테이블을 생성/삭제하지 않음
#
#     def save(self, *args, **kwargs):
#         # 8자리 날짜 형식 강제 (SQL 스키마 일치)
#         if self.last_login and not isinstance(self.last_login, str):
#             self.last_login = self.last_login.strftime('%Y%m%d')
#         super().save(*args, **kwargs)
#
# # ⭐ 이 모델이 누락되어 ImportError가 발생했던 것입니다. ⭐
# class LoginHistory(models.Model):
#     # SQL: LOGIN_TH
#     cust = models.ForeignKey(Cust, on_delete=models.CASCADE, db_column='cust_id', primary_key=True)
#     login_dt = models.CharField(max_length=8)
#     seq = models.BigIntegerField()
#     login_time = models.CharField(max_length=14, null=True, blank=True)
#     logout_time = models.CharField(max_length=14, null=True, blank=True)
#     success_yn = models.CharField(max_length=1, null=True, blank=True)
#     created_time = models.CharField(max_length=14, null=True, blank=True)
#     updated_time = models.CharField(max_length=14, null=True, blank=True)
#
#     class Meta:
#         db_table = 'LOGIN_TH'
#         managed = False
#         unique_together = (('cust', 'login_dt', 'seq'),)
#
# class CusProfile(models.Model):
#     # SQL: CUS_PROFILE_TS
#     cust = models.OneToOneField(Cust, on_delete=models.CASCADE, primary_key=True, db_column='cust_id')
#     height_cm = models.DecimalField(max_digits=10, decimal_places=2, null=True)
#     weight_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True)
#     bmi = models.DecimalField(max_digits=10, decimal_places=2, null=True)
#     bmr = models.DecimalField(max_digits=10, decimal_places=2, null=True)
#     gender = models.CharField(max_length=1, null=True)
#     birth_dt = models.CharField(max_length=8, null=True)
#     ratio_carb = models.IntegerField(db_column='Ratio_carb', null=True)
#     ratio_protein = models.IntegerField(db_column='Ratio_protein', null=True)
#     ratio_fat = models.IntegerField(db_column='Ratio_fat', null=True)
#     activity_level = models.CharField(max_length=1, null=True)
#     purpose = models.CharField(max_length=1, null=True)
#     calories_burned = models.DecimalField(max_digits=7, decimal_places=2, db_column='Calories_burned', null=True)
#     recommended_calories = models.DecimalField(max_digits=7, decimal_places=2, db_column='Recommended_calories', null=True)
#     offset = models.FloatField(db_column='Offset', null=True)
#     created_time = models.CharField(max_length=14, null=True)
#     updated_time = models.CharField(max_length=14, null=True)
#
#     class Meta:
#         db_table = 'CUS_PROFILE_TS'
#         managed = False

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
import datetime

# #### 1. 커스텀 유저 매니저 정의 (get_by_natural_key 오류 해결 핵심) ####
class CustManager(BaseUserManager):
    """
    BaseUserManager를 상속받아 Django의 Authentication System과
    연동되는 Custom Manager입니다.
    """
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        # Admin 기능을 위해 필요한 경우 작성 (managed=False이므로 DB 반영은 안 됨)
        user = self.create_user(email, password, **extra_fields)
        return user

    # authenticate() 함수가 호출하는 핵심 메서드
    def get_by_natural_key(self, username):
        return self.get(**{self.model.USERNAME_FIELD: username})

# #### 2. 커스텀 유저 모델 (CUST_TM) ####
class Cust(AbstractBaseUser):
    # SQL: CUST_TM
    cust_id = models.CharField(max_length=10, primary_key=True)
    email = models.CharField(max_length=254, unique=True)
    password = models.CharField(max_length=1000)
    created_dt = models.CharField(max_length=8, null=True, blank=True)
    # Django 기본 last_login 필드를 CharField(db_column='last_login_dt')로 오버라이드
    last_login = models.CharField(max_length=8, null=True, blank=True, db_column='last_login_dt')
    updated_dt = models.CharField(max_length=8, null=True, blank=True)
    leave_dt = models.CharField(max_length=8, null=True, blank=True)
    retry_cnt = models.IntegerField(default=0, null=True, blank=True)
    lock_yn = models.CharField(max_length=1, default='N', null=True, blank=True)
    created_time = models.CharField(max_length=14, null=True, blank=True)
    updated_time = models.CharField(max_length=14, null=True, blank=True)

    # ⭐ 핵심: 정의한 매니저를 연결해야 authenticate()가 정상 작동합니다.
    objects = CustManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'CUST_TM'
        managed = False  # ⭐ 기존 테이블을 사용하므로 Django가 관리하지 않음

    def save(self, *args, **kwargs):
        # 8자리 날짜 형식 강제 (SQL 스키마 일치)
        if self.last_login and not isinstance(self.last_login, str):
            self.last_login = self.last_login.strftime('%Y%m%d')
        super().save(*args, **kwargs)

# #### 3. 로그인 이력 모델 (LOGIN_TH) ####
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

# #### 4. 고객 프로필 모델 (CUS_PROFILE_TS) ####
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