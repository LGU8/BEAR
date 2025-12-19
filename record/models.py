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
