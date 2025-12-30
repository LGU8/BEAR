from django.db import models


class CusFeelTh(models.Model):
    cust_id = models.CharField(max_length=10)
    rgs_dt = models.CharField(max_length=8)

    seq = models.BigIntegerField(primary_key=True)  # ✅ 이 줄만 핵심

    time_slot = models.CharField(max_length=1)
    mood = models.CharField(max_length=3)
    energy = models.CharField(max_length=3)
    cluster_val = models.CharField(max_length=1, null=True, blank=True)
    stable_yn = models.CharField(max_length=1, null=True, blank=True)

    class Meta:
        db_table = "CUS_FEEL_TH"
        managed = False


class ReportTh(models.Model):
    # 공통 컬럼
    created_time = models.CharField(max_length=14, null=True, blank=True)
    updated_time = models.CharField(max_length=14, null=True, blank=True)

    # 논리 PK 구성요소
    cust_id = models.CharField(max_length=10, primary_key=True)
    rgs_dt = models.CharField(max_length=8)
    type = models.CharField(max_length=1)  # D/W

    # 기간
    period_start = models.CharField(max_length=8, null=True, blank=True)  # YYYYMMDD
    period_end = models.CharField(max_length=8, null=True, blank=True)  # YYYYMMDD

    # 내용
    content = models.CharField(max_length=4000, null=True, blank=True)

    class Meta:
        db_table = "REPORT_TH"
        managed = False
        # 논리적인 유니크 제약(복합PK 의미)
        constraints = [
            models.UniqueConstraint(
                fields=["cust_id", "rgs_dt", "type"], name="uq_report_th_cust_rgs_type"
            )
        ]


class FoodTb(models.Model):
    created_time = models.CharField(max_length=14, null=True, blank=True)
    updated_time = models.CharField(max_length=14, null=True, blank=True)
    food_id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=40, blank=True)

    kcal = models.IntegerField(null=True, blank=True)
    carb_g = models.IntegerField(null=True, blank=True)
    protein_g = models.IntegerField(null=True, blank=True)
    fat_g = models.IntegerField(null=True, blank=True)

    Macro_ratio_c = models.IntegerField(null=True, blank=True)
    Macro_ratio_p = models.IntegerField(null=True, blank=True)
    Macro_ratio_f = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "FOOD_TB"
        managed = (
            False  # 이미 DB에 테이블이 있으니 Django가 마이그레이션으로 건드리지 않게
        )


class CusFoodTh(models.Model):
    created_time = models.CharField(max_length=14, null=True, blank=True)
    updated_time = models.CharField(max_length=14, null=True, blank=True)

    cust_id = models.CharField(max_length=10, primary_key=True)
    rgs_dt = models.CharField(max_length=8)
    seq = models.IntegerField()
    time_slot = models.CharField(max_length=10, null=True)

    kcal = models.IntegerField(null=True, blank=True)
    carb_g = models.IntegerField(null=True, blank=True)
    protein_g = models.IntegerField(null=True, blank=True)
    fat_g = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "CUS_FOOD_TH"
        managed = False


class CusFoodTs(models.Model):
    created_time = models.CharField(max_length=14, null=True, blank=True)
    updated_time = models.CharField(max_length=14, null=True, blank=True)

    cust_id = models.CharField(max_length=10, primary_key=True)
    rgs_dt = models.CharField(max_length=8)
    seq = models.IntegerField()

    food_seq = models.IntegerField()
    food_id = models.CharField(max_length=10, null=True)

    class Meta:
        db_table = "CUS_FOOD_TS"
        managed = False
