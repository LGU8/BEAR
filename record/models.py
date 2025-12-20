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
