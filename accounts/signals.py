# accounts/signals.py
from __future__ import annotations

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.db import IntegrityError, transaction
from datetime import datetime

from accounts.models import CusBadge

LOGIN_BADGE_ID = "E000000031"


def _now_yyyymmddhhmmss() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def grant_login_badge(cust_id: str) -> bool:
    """
    로그인 배지 1회 지급.
    - 이미 있으면 False
    - 신규 지급이면 True
    - DB Unique 제약 + IntegrityError 처리로 race condition에도 안전
    """
    if not cust_id:
        return False

    try:
        with transaction.atomic():
            # (1) 빠른 선조회 (UX/로그 목적)
            if CusBadge.objects.filter(cust_id=cust_id, badge_id=LOGIN_BADGE_ID).exists():
                return False

            # (2) insert
            CusBadge.objects.create(
                cust_id=cust_id,
                badge_id=LOGIN_BADGE_ID,
                acquired_time=_now_yyyymmddhhmmss(),
            )
            return True

    except IntegrityError:
        # 동시 로그인 등으로 거의 동시에 insert가 들어온 케이스
        # UNIQUE(cust_id,badge_id)가 DB에 있으면 여기로 떨어지고, “이미 지급됨” 취급
        return False


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    """
    Django 로그인 성공 시 자동 호출
    - user.cust_id 우선
    - 없으면 session fallback
    """
    cust_id = getattr(user, "cust_id", None)
    if not cust_id:
        cust_id = request.session.get("cust_id")

    if cust_id:
        grant_login_badge(str(cust_id))
