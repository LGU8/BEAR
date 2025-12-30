# accounts/views.py
from __future__ import annotations

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

from .models import Cust, CusProfile, LoginHistory


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
        return str(user.pk) + str(timestamp) + str(user.password)


account_activation_token = AccountActivationTokenGenerator()


# =========================
# 2) cust_id 생성
# =========================
def generate_new_cust_id() -> str:
    """
    CUST_TM.cust_id가 VARCHAR(10)이며 숫자형 문자열이라는 가정.
    max(cust_id) + 1 방식.
    """
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

        user = authenticate(request, username=email, password=password)

        if user is None:
            return render(
                request,
                "accounts/login.html",
                {"error_message": "이메일 또는 비밀번호가 올바르지 않습니다.", "email": email},
            )

        # 1) Django session login
        login(request, user)

        # 2) 세션 cust_id 저장 (settings 등 다른 앱에서 fallback으로 사용)
        request.session["cust_id"] = str(user.cust_id)

        # 3) 시각 파트
        today_8, now_14, time_6 = _now_parts()

        # 4) CUST_TM last_login_dt / updated_dt / updated_time 갱신
        user.last_login = today_8  # db_column='last_login_dt'
        user.updated_dt = today_8
        user.updated_time = now_14
        user.save(update_fields=["last_login", "updated_dt", "updated_time"])

        # 5) LOGIN_TH 기록 (seq 증가)
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
            # 로그인 자체는 성공했지만, 이력 저장만 실패한 케이스
            print(f"[LoginHistory] Save Error: {e}")

        # 6) redirect
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
            # 로그아웃 시간 업데이트
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
# 6) PASSWORD RESET
# =========================
def password_reset(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        try:
            user = Cust.objects.get(email=email)

            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = account_activation_token.make_token(user)

            reset_link = f"http://127.0.0.1:8000/accounts/password-reset-confirm/{uid}/{token}/"

            send_mail(
                "[BEAR] 비밀번호 재설정 안내",
                f"아래 링크를 클릭하여 비밀번호를 변경하세요.\n\n{reset_link}",
                from_email=None,
                recipient_list=[email],
                fail_silently=False,
            )
            return render(request, "accounts/password_reset_done.html")

        except Cust.DoesNotExist:
            return render(
                request,
                "accounts/password_reset.html",
                {"error": "존재하지 않는 이메일입니다."},
            )

    return render(request, "accounts/password_reset.html")


def password_reset_confirm(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = Cust.objects.get(pk=uid)
    except Exception:
        user = None

    if not (user and account_activation_token.check_token(user, token)):
        return render(request, "accounts/password_reset_error.html")

    if request.method == "POST":
        new_pw = (request.POST.get("new_password") or "").strip()
        if not new_pw:
            return render(request, "accounts/password_reset_confirm.html", {"error": "비밀번호를 입력해주세요."})

        today_8, now_14, _ = _now_parts()

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
            return render(request, "accounts/signup_step1.html", {"error": "이메일과 비밀번호를 입력해주세요."})

        if Cust.objects.filter(email=email).exists():
            return render(request, "accounts/signup_step1.html", {"error": "이미 가입된 이메일입니다."})

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
            return render(request, "accounts/signup_step3.html", {"error": "선호도 값이 올바르지 않습니다."})

        s = c + p + f
        if s != 10:
            return render(request, "accounts/signup_step3.html", {"error": "탄/단/지 합계가 10이 되도록 선택해주세요."})

        request.session["pref_carb"] = c
        request.session["pref_protein"] = p
        request.session["pref_fat"] = f

        print("[SIGNUP_STEP3] posted:", c, p, f, "sum=", (c + p + f))
        print("[SIGNUP_STEP3] session_saved:",
              request.session.get("pref_carb"),
              request.session.get("pref_protein"),
              request.session.get("pref_fat"))

        return redirect("accounts_app:signup_step4")

    context = {
        "pref_carb": request.session.get("pref_carb", 0),
        "pref_protein": request.session.get("pref_protein", 0),
        "pref_fat": request.session.get("pref_fat", 0),
    }

    return render(request, "accounts/signup_step3.html")


# --- 계산 로직 ---
ACTIVITY_FACTOR = {"0": 1.2, "1": 1.375, "2": 1.55, "3": 1.725}
OFFSET_MAP = {"0": -400, "1": 0, "2": 400}


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
    return (round(carb / total * 100), round(protein / total * 100), round(fat / total * 100))

from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render

@transaction.atomic
def signup_step4(request):
    ctx = {
        "activity_level": str(request.session.get("activity_level", "")),
        "purpose": str(request.session.get("purpose", "")),
        "error": "",
    }

    if request.method != "POST":
        return render(request, "accounts/signup_step4.html", ctx)

    # Step1 세션 필수값
    email = request.session.get("reg_email")
    password = request.session.get("reg_password")
    if not email or not password:
        return redirect("accounts_app:signup_step1")

    # POST 값
    activity_level = str((request.POST.get("activity_level") or "").strip())
    purpose = str((request.POST.get("purpose") or "").strip())

    # ctx에 즉시 반영 (POST 실패 시 복원)
    ctx["activity_level"] = activity_level
    ctx["purpose"] = purpose

    # 필수 선택 검증
    if activity_level not in ACTIVITY_FACTOR:
        ctx["error"] = "활동량을 선택해주세요."
        return render(request, "accounts/signup_step4.html", ctx)

    if purpose not in OFFSET_MAP:
        ctx["error"] = "목표를 선택해주세요."
        return render(request, "accounts/signup_step4.html", ctx)

    # 세션 저장 (뒤로가기/새로고침 대비)
    request.session["activity_level"] = activity_level
    request.session["purpose"] = purpose

    # 이전 step 세션 로드
    try:
        raw_birth_dt = (request.session.get("birth_dt") or "").replace("-", "")
        gender = (request.session.get("gender") or "M").strip()
        height = float(request.session.get("height_cm") or 0)
        weight = float(request.session.get("weight_kg") or 0)

        pref_carb = int(request.session.get("pref_carb", 5))
        pref_protein = int(request.session.get("pref_protein", 5))
        pref_fat = int(request.session.get("pref_fat", 5))
    except Exception as e:
        print(f"[Signup] Session data error: {e}")
        return redirect("accounts_app:signup_step2")

    try:
        age = calc_age(raw_birth_dt)
        bmi = calc_bmi(weight, height)
        bmr = calc_bmr(gender, weight, height, age)
        tdee = calc_tdee(bmr, activity_level)
        recommended, offset = calc_recommended_calories(tdee, purpose)

        # Ratio 저장 정책: 점수 그대로(1~10)
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
        print(f"[Signup] IntegrityError: {e}")
        ctx["error"] = "가입 처리 중 중복/제약 오류가 발생했습니다."
        return render(request, "accounts/signup_step4.html", ctx)

    except Exception as e:
        print(f"[Signup] Final Error: {e}")
        ctx["error"] = f"가입 처리 중 오류 발생: {e}"
        return render(request, "accounts/signup_step4.html", ctx)


# =========================
# 8) TEST LOGIN
# =========================
def test_login_view(request):
    test_email = "test@test"
    test_password = "11111111"

    user = authenticate(request, username=test_email, password=test_password)
    if user is not None:
        login(request, user)
        return redirect("home")

    messages.error(request, "테스트 계정이 존재하지 않습니다. 관리자에게 문의하세요.")
    return redirect("accounts_app:user_login")
