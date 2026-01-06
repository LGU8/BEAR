# accounts/views.py
from __future__ import annotations

import logging
from datetime import date
from typing import Tuple

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.urls import reverse

from .models import Cust, CusProfile, LoginHistory

logger = logging.getLogger(__name__)


# =========================
# 0) 공용 유틸
# =========================
def _now_parts() -> Tuple[str, str, str]:
    """
    return: (today_8, now_14, time_6)
    - today_8: YYYYMMDD
    - now_14 : YYYYMMDDHHMMSS
    - time_6 : HHMMSS
    """
    now = timezone.now()
    return (
        now.strftime("%Y%m%d"),
        now.strftime("%Y%m%d%H%M%S"),
        now.strftime("%H%M%S"),
    )


def _safe_int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# =========================
# 1) Token Generator (PW Reset)
# =========================
class AccountActivationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        # ✅ password가 바뀌면 기존 토큰이 무효화되도록 포함
        return str(user.pk) + str(timestamp) + str(user.password)


account_activation_token = AccountActivationTokenGenerator()


# =========================
# 1-1) Password Reset URL Builder
# =========================
def _build_password_reset_link(request, uidb64: str, token: str) -> str:
    """
    ✅ 코드에 EB 링크 하드코딩 금지
    ✅ 현재 요청 host/scheme 기반 absolute url 생성

    - EB 뒤에서 https 인식은 settings의
      SECURE_PROXY_SSL_HEADER / USE_X_FORWARDED_HOST가 잡아줌
    """
    # urls.py: path("password-reset-confirm/<uidb64>/<token>/", ...)
    rel_path = reverse("accounts_app:password_reset_confirm", kwargs={"uidb64": uidb64, "token": token})

    # ✅ 혹시 EB에서 scheme이 http로 잡히는 케이스를 "보정"하고 싶다면(옵션)
    # if not settings.DEBUG and request.META.get("HTTP_X_FORWARDED_PROTO") == "https":
    #     url = url.replace("http://", "https://", 1)

    return request.build_absolute_uri(rel_path)

# =========================
# 2) cust_id 생성
# =========================
def generate_new_cust_id() -> str:
    max_id_str = Cust.objects.all().aggregate(Max("cust_id"))["cust_id__max"]
    if max_id_str:
        new_id_int = int(max_id_str) + 1
        return str(new_id_int).zfill(10)
    return "0000000001"


# =========================
# 3) LOGIN
# =========================
def user_login(request):
    next_url = request.GET.get("next", "")

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        password = (request.POST.get("password") or "").strip()

        logger.warning("[LOGINDBG] POST email=%s", email)
        logger.warning("[LOGINDBG] cookie sessionid(before)=%s", request.COOKIES.get("sessionid"))
        logger.warning("[LOGINDBG] host=%s scheme=%s secure=%s",
                       request.get_host(),
                       request.scheme,
                       request.is_secure())

        user = authenticate(request, username=email, password=password)

        logger.warning("[LOGINDBG] authenticate result user_cust_id=%s user_email=%s",
                       getattr(user, "cust_id", None),
                       getattr(user, "email", None))

        if user is None:
            return render(
                request,
                "accounts/login.html",
                {"error_message": "이메일 또는 비밀번호가 올바르지 않습니다.", "email": email},
            )

        login(request, user)

        logger.warning("[LOGINDBG] after login request.user.cust_id=%s request.user.email=%s",
                       getattr(request.user, "cust_id", None),
                       getattr(request.user, "email", None))
        logger.warning("[LOGINDBG] session_key(after login)=%s", request.session.session_key)
        logger.warning("[LOGINDBG] _auth_user_id in session=%s", request.session.get("_auth_user_id"))
        logger.warning("[LOGINDBG] session keys=%s", list(request.session.keys()))

        request.session["cust_id"] = str(request.user.cust_id)

        logger.warning("[LOGINDBG] session cust_id(after set)=%s", request.session.get("cust_id"))

        today_8, now_14, time_6 = _now_parts()

        user.last_login = today_8
        user.updated_dt = today_8
        user.updated_time = now_14
        user.save(update_fields=["last_login", "updated_dt", "updated_time"])

        try:
            max_seq = (
                LoginHistory.objects.filter(cust=user).aggregate(Max("seq"))["seq__max"] or 0
            )
            new_seq = max_seq + 1

            LoginHistory.objects.create(
                cust=user,
                seq=new_seq,
                login_dt=today_8,
                login_time=time_6,
                success_yn="Y",
                created_time=now_14,
                updated_time=now_14,
            )

            request.session["current_login_seq"] = new_seq

        except Exception as e:
            logger.warning("[LOGINDBG] LoginHistory save error: %r", e)

        if next_url:
            return redirect(next_url)
        return redirect("home")

    return render(request, "accounts/login.html")


# =========================
# 4) LOGOUT
# =========================
def user_logout(request):
    if request.method != "POST":
        return redirect("root")

    user = request.user
    if user.is_authenticated:
        today_8, now_14, time_6 = _now_parts()
        current_seq = request.session.get("current_login_seq")

        if current_seq:
            LoginHistory.objects.filter(
                cust=user,
                login_dt=today_8,
                seq=current_seq,
            ).update(
                logout_time=time_6,
                updated_time=now_14,
            )

        logout(request)

    return redirect("root")


# =========================
# 5) PROFILE / HOME
# =========================
@login_required(login_url="accounts_app:user_login")
def profile(request):
    return render(request, "accounts/profile.html", {"user": request.user})


def home(request):
    return render(request, "accounts/home.html")


# =========================
# 6) PASSWORD RESET (실기능)
# =========================
def password_reset(request):
    """
    UI -> 실제 메일 발송 기능으로 동작
    """
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()

        if not email:
            return render(request, "accounts/password_reset.html", {"error": "이메일을 입력해주세요."})

        try:
            user = Cust.objects.get(email=email)

            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = account_activation_token.make_token(user)

            reset_link = _build_password_reset_link(request, uidb64, token)

            # ✅ 운영에서 메일 설정 누락 시 바로 감지할 수 있도록 로그
            logger.warning("[PWRESET] email=%s host=%s scheme=%s is_secure=%s xfp=%s link=%s",
                           email,
                           request.get_host(),
                           request.scheme,
                           request.is_secure(),
                           request.META.get("HTTP_X_FORWARDED_PROTO"),
                           reset_link)

            subject = "[BEAR] 비밀번호 재설정 안내"
            message = (
                "아래 링크를 클릭하여 비밀번호를 변경하세요.\n\n"
                f"{reset_link}\n\n"
                "만약 본인이 요청하지 않았다면 이 메일을 무시해주세요."
            )

            # ✅ DEFAULT_FROM_EMAIL은 settings에서 env로 받아옴
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "no-reply@bear.local",
                    recipient_list=[email],
                    fail_silently=getattr(settings, "EMAIL_FAIL_SILENTLY", False),
                )
            except Exception:
                logger.exception("[PWRESET] send_mail failed: email=%s host=%s", email, request.get_host())
                return render(
                    request,
                    "accounts/password_reset.html",
                    {
                        "email": email,
                        "error": "메일 전송에 실패했습니다. 잠시 후 다시 시도해 주세요. 문제가 계속되면 관리자에게 문의해 주세요.",
                    },
                )
            else:
                return render(request, "accounts/password_reset_done.html")



        except Cust.DoesNotExist:
            return render(
                request,
                "accounts/password_reset.html",
                {"error": "존재하지 않는 이메일입니다."},
            )
        except Exception as e:
            # SMTP 설정/네트워크/인증 실패 등
            logger.exception("[PWRESET] send_mail failed: %r", e)
            return render(
                request,
                "accounts/password_reset.html",
                {"error": "메일 발송에 실패했습니다. 잠시 후 다시 시도해주세요."},
            )

    return render(request, "accounts/password_reset.html")


def password_reset_confirm(request, uidb64, token):
    """
    링크 클릭 -> 토큰 검증 -> 새 비밀번호 저장
    """
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = Cust.objects.get(pk=uid)
    except Exception:
        user = None

    if not (user and account_activation_token.check_token(user, token)):
        return render(request, "accounts/password_reset_error.html")

    if request.method == "POST":
        new_pw = (request.POST.get("new_password") or "").strip()
        confirm_pw = (request.POST.get("confirm_password") or "").strip()

        if not new_pw:
            return render(
                request,
                "accounts/password_reset_confirm.html",
                {"error": "비밀번호를 입력해주세요."},
            )

        if new_pw != confirm_pw:
            return render(
                request,
                "accounts/password_reset_confirm.html",
                {"error": "비밀번호 확인이 일치하지 않습니다."},
            )

        today_8, now_14, _ = _now_parts()

        # ✅ Django make_password(PBKDF2)로 저장 (현재 CustBackend가 check_password 사용중이므로 정합)
        user.password = make_password(new_pw)
        user.updated_dt = today_8
        user.updated_time = now_14
        user.save(update_fields=["password", "updated_dt", "updated_time"])

        return redirect("accounts_app:user_login")

    return render(request, "accounts/password_reset_confirm.html")


# =========================
# 7) SIGNUP (Step 1~4)
# =========================
def signup_step1(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        password = (request.POST.get("password") or "").strip()

        if not email or not password:
            return render(
                request,
                "accounts/signup_step1.html",
                {"error": "이메일과 비밀번호를 입력해주세요."},
            )

        if Cust.objects.filter(email=email).exists():
            return render(
                request,
                "accounts/signup_step1.html",
                {"error": "이미 가입된 이메일입니다."},
            )

        secure_password = make_password(password)
        request.session["reg_email"] = email
        request.session["reg_password"] = secure_password

        return redirect("accounts_app:signup_step2")

    return render(request, "accounts/signup_step1.html")


def signup_step2(request):
    if not request.session.get("reg_email"):
        return redirect("accounts_app:signup_step1")

    if request.method == "POST":
        request.session["gender"] = (request.POST.get("gender") or "M").strip()
        request.session["birth_dt"] = (request.POST.get("birth_dt") or "").replace("-", "")
        request.session["height_cm"] = (request.POST.get("height_cm") or "").strip()
        request.session["weight_kg"] = (request.POST.get("weight_kg") or "").strip()

        return redirect("accounts_app:signup_step3")

    return render(request, "accounts/signup_step2.html")


def signup_step3(request):
    if not request.session.get("reg_email"):
        return redirect("accounts_app:signup_step1")

    if request.method == "POST":
        c = _safe_int(request.POST.get("ratio_carb"), 0)
        p = _safe_int(request.POST.get("ratio_protein"), 0)
        f = _safe_int(request.POST.get("ratio_fat"), 0)

        if not (0 <= c <= 10 and 0 <= p <= 10 and 0 <= f <= 10):
            return render(
                request,
                "accounts/signup_step3.html",
                {"error": "선호도 값이 올바르지 않습니다."},
            )

        s = c + p + f
        if s != 10:
            return render(
                request,
                "accounts/signup_step3.html",
                {"error": "탄/단/지 합계가 10이 되도록 선택해주세요."},
            )

        request.session["pref_carb"] = c
        request.session["pref_protein"] = p
        request.session["pref_fat"] = f

        logger.warning("[SIGNUP_STEP3] posted: %s %s %s sum=%s", c, p, f, (c + p + f))
        logger.warning(
            "[SIGNUP_STEP3] session_saved: %s %s %s",
            request.session.get("pref_carb"),
            request.session.get("pref_protein"),
            request.session.get("pref_fat"),
        )

        return redirect("accounts_app:signup_step4")

    context = {
        "pref_carb": request.session.get("pref_carb", 0),
        "pref_protein": request.session.get("pref_protein", 0),
        "pref_fat": request.session.get("pref_fat", 0),
    }

    return render(request, "accounts/signup_step3.html", context)


ACTIVITY_FACTOR = {"1": 1.2, "2": 1.375, "3": 1.55, "4": 1.725}
OFFSET_MAP = {"1": -400, "2": 0, "3": 400}


def calc_age(birth_dt: str) -> int:
    if not birth_dt or len(birth_dt) != 8 or not birth_dt.isdigit():
        return 0
    try:
        birth = date(int(birth_dt[:4]), int(birth_dt[4:6]), int(birth_dt[6:8]))
        today = date.today()
        return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    except Exception:
        return 0


def calc_bmi(weight_kg: float, height_cm: float) -> float:
    if height_cm <= 0:
        return 0.0
    height_m = height_cm / 100
    return round(weight_kg / (height_m**2), 2)


def calc_bmr(gender: str, weight: float, height: float, age: int) -> float:
    try:
        weight = float(weight)
        height = float(height)
        age = int(age)
    except Exception:
        return 0.0

    if gender == "M":
        return round(66.47 + (13.75 * weight) + (5 * height) - (6.76 * age), 2)
    if gender == "F":
        return round(655.1 + (9.56 * weight) + (1.85 * height) - (4.68 * age), 2)
    return 0.0


def calc_tdee(bmr: float, activity_level: str) -> float:
    factor = ACTIVITY_FACTOR.get(activity_level, 1.375)
    return round(bmr * factor, 2)


def calc_recommended_calories(tdee: float, purpose: str) -> Tuple[float, int]:
    offset = OFFSET_MAP.get(purpose, 0)
    return tdee + offset, offset


def calc_macro_ratio(carb: int, protein: int, fat: int) -> Tuple[int, int, int]:
    total = carb + protein + fat
    if total == 0:
        return (33, 34, 33)
    return (
        round(carb / total * 100),
        round(protein / total * 100),
        round(fat / total * 100),
    )


@transaction.atomic
def signup_step4(request):
    ctx = {
        "activity_level": str(request.session.get("activity_level", "")),
        "purpose": str(request.session.get("purpose", "")),
        "error": "",
    }

    if request.method != "POST":
        return render(request, "accounts/signup_step4.html", ctx)

    email = request.session.get("reg_email")
    password = request.session.get("reg_password")
    if not email or not password:
        return redirect("accounts_app:signup_step1")

    activity_level = str((request.POST.get("activity_level") or "").strip())
    purpose = str((request.POST.get("purpose") or "").strip())

    ctx["activity_level"] = activity_level
    ctx["purpose"] = purpose

    if activity_level not in ACTIVITY_FACTOR:
        ctx["error"] = "활동량을 선택해주세요."
        return render(request, "accounts/signup_step4.html", ctx)

    if purpose not in OFFSET_MAP:
        ctx["error"] = "목표를 선택해주세요."
        return render(request, "accounts/signup_step4.html", ctx)

    request.session["activity_level"] = activity_level
    request.session["purpose"] = purpose

    try:
        raw_birth_dt = (request.session.get("birth_dt") or "").replace("-", "")
        gender = (request.session.get("gender") or "M").strip()
        height = float(request.session.get("height_cm") or 0)
        weight = float(request.session.get("weight_kg") or 0)

        pref_carb = int(request.session.get("pref_carb", 5))
        pref_protein = int(request.session.get("pref_protein", 5))
        pref_fat = int(request.session.get("pref_fat", 5))
    except Exception as e:
        logger.warning("[Signup] Session data error: %r", e)
        return redirect("accounts_app:signup_step2")

    try:
        age = calc_age(raw_birth_dt)
        bmi = calc_bmi(weight, height)
        bmr = calc_bmr(gender, weight, height, age)
        tdee = calc_tdee(bmr, activity_level)
        recommended, offset = calc_recommended_calories(tdee, purpose)

        ratio_c, ratio_p, ratio_f = pref_carb, pref_protein, pref_fat

        today_8, now_14, _ = _now_parts()
        new_cust_id = generate_new_cust_id()

        new_user = Cust.objects.create(
            cust_id=new_cust_id,
            email=email,
            password=password,
            created_dt=today_8,
            updated_dt=today_8,
            created_time=now_14,
            updated_time=now_14,
            retry_cnt=0,
            lock_yn="N",
        )

        CusProfile.objects.create(
            cust=new_user,
            height_cm=height,
            weight_kg=weight,
            bmi=bmi,
            bmr=bmr,
            gender=gender,
            birth_dt=raw_birth_dt,
            ratio_carb=ratio_c,
            ratio_protein=ratio_p,
            ratio_fat=ratio_f,
            activity_level=activity_level,
            purpose=purpose,
            calories_burned=tdee,
            recommended_calories=recommended,
            offset=offset,
            created_time=now_14,
            updated_time=now_14,
        )

        request.session.flush()
        return redirect("accounts_app:user_login")

    except IntegrityError as e:
        logger.warning("[Signup] IntegrityError: %r", e)
        ctx["error"] = "가입 처리 중 중복/제약 오류가 발생했습니다."
        return render(request, "accounts/signup_step4.html", ctx)

    except Exception as e:
        logger.warning("[Signup] Final Error: %r", e)
        ctx["error"] = f"가입 처리 중 오류 발생: {e}"
        return render(request, "accounts/signup_step4.html", ctx)


def test_login_view(request):
    test_email = "test@test"
    test_password = "11111111"

    user = authenticate(request, username=test_email, password=test_password)
    if user is not None:
        login(request, user)
        return redirect("home")

    messages.error(request, "테스트 계정이 존재하지 않습니다. 관리자에게 문의하세요.")
    return redirect("accounts_app:user_login")