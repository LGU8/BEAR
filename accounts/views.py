from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect
from django.utils import timezone
from django.db.models import Max
from django.db import IntegrityError, transaction
from .models import Cust, LoginHistory, CusProfile
import hashlib
from django.contrib.auth.models import User
from datetime import date
import hashlib  # ⭐ 이 라인을 추가합니다.
from django.shortcuts import render, redirect
from django.contrib.auth.hashers import make_password # SHA256 대신 이걸 사용
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.conf import settings  # settings.LOGIN_REDIRECT_URL 사용을 위해 필요

# settings.py에 LOGIN_REDIRECT_URL = 'profile' 설정을 추가했다고 가정


# cust_id를 생성하는 도우미 함수 (cust_id가 VARCHAR이므로 문자열로 처리)
def generate_new_cust_id():
    """현재 DB의 최대 cust_id를 찾아 1 증가시킨 새 ID를 반환 (VARCHAR 처리)"""
    # 현재 cust_id의 최댓값을 가져옵니다.
    # Cust.objects.all()에서 Max를 사용해야 합니다.
    max_id_str = Cust.objects.all().aggregate(Max("cust_id"))["cust_id__max"]

    if max_id_str:
        # 문자열을 숫자로 변환 후 1 증가
        new_id_int = int(max_id_str) + 1
        # 다시 VARCHAR(10)에 맞게 문자열로 포맷팅 (예: 0000000001, 0000000010 등)
        # cust_id가 10자리 문자열이라고 가정하고, 0으로 채웁니다.
        # 실제 데이터 포맷에 따라 이 부분이 달라질 수 있습니다.
        new_cust_id = str(new_id_int).zfill(10)
    else:
        # 테이블이 비어있으면 1번 ID (0000000001)부터 시작
        new_cust_id = "0000000001"

    return new_cust_id


# 1. 로그인 뷰 (GET 요청: 폼 표시, POST 요청: 인증 처리)
# accounts/views.py - user_login 함수
#
# def user_login(request):
#     if request.method == "POST":
#         email = request.POST.get("email")
#         password = request.POST.get("password")
#
#         # 로그인 시도 전 URL에 담긴 'next' 경로를 가져옵니다.
#         next_url = request.GET.get('next')
#
#         user = authenticate(request, username=email, password=password)
#
#         if user is not None:
#             login(request, user)
#
#             # 1순위: 가려던 페이지(next)가 있다면 그곳으로 이동
#             # 2순위: 없다면 기본 프로필 페이지로 이동
#             if next_url:
#                 return redirect(next_url)
#             return redirect("accounts_app:profile")
#         else:
#             return render(request, "accounts/login.html", {"error_message": "이메일 또는 비밀번호가 틀렸습니다."})
#
#     return render(request, "accounts/login.html")

from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.utils import timezone
from django.db.models import Max
from .models import LoginHistory


def user_login(request):
    next_url = request.GET.get('next', '')

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, username=email, password=password)

        if user is not None:
            # 1. 장고 세션 로그인
            login(request, user)

            # 2. 로그인 이력 생성을 위한 정보 준비
            max_seq = LoginHistory.objects.filter(cust=user).aggregate(Max('seq'))['seq__max'] or 0
            new_seq = max_seq + 1

            now = timezone.now()
            today_str = now.strftime('%Y%m%d')
            time_str = now.strftime('%H%M%S')

            # 3. DB에 로그인 기록 저장
            try:
                LoginHistory.objects.create(
                    cust=user,
                    seq=new_seq,
                    login_dt=today_str,
                    login_time=time_str,
                    success_yn="Y"
                )

                # ⭐ 핵심: 현재 생성된 seq를 세션에 저장하여 로그아웃 때 사용함
                request.session['current_login_seq'] = new_seq

            except Exception as e:
                print(f"Login History Save Error: {e}")

            # 4. 리다이렉트
            if next_url:
                return redirect(next_url)
            return redirect("home")
        else:
            return render(request, "accounts/login.html", {
                "error_message": "이메일 또는 비밀번호가 올바르지 않습니다.",
                "email": email
            })

    return render(request, "accounts/login.html")


def user_logout(request):
    if request.method == "POST":
        user = request.user
        if user.is_authenticated:
            # ⭐ 로그인할 때 세션에 담아뒀던 seq 번호를 가져옴
            current_seq = request.session.get('current_login_seq')

            now = timezone.now()
            today_str = now.strftime('%Y%m%d')
            time_str = now.strftime('%H%M%S')

            if current_seq:
                # 1. 세션에 저장된 seq와 일치하는 '딱 하나의 행'만 업데이트
                # filter(...).update(...)를 사용하여 중복 PK 에러 원천 차단
                LoginHistory.objects.filter(
                    cust=user,
                    login_dt=today_str,
                    seq=current_seq
                ).update(logout_time=time_str)

            # 2. 장고 세션 로그아웃 (세션 데이터가 삭제됨)
            logout(request)

        return redirect("root")



# 3. 프로필 뷰 (로그인 필요)
@login_required
def profile(request):
    # 로그인된 사용자 정보가 request.user에 담겨 템플릿으로 전달됨
    return render(request, "accounts/profile.html", {"user": request.user})


# 4. 홈 뷰 (제공해주신 home.html을 렌더링)
def home(request):
    return render(request, "accounts/home.html")


import secrets
import string


def password_reset():
    return "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(10)
    )


import hashlib
from datetime import date
from django.shortcuts import render, redirect

# from django.utils import timezone # created_dt를 오늘 날짜로 단순화하여 사용하지 않음
from django.db import IntegrityError  # DB 에러 처리를 위해 추가
from .models import Cust, CusProfile  # 모델 import 확인

from django.contrib.auth.hashers import make_password  # ⭐ 추가: Django 암호화 함수
# import hashlib  <-- 이제 단순 SHA256은 사용하지 않으므로 필요 없습니다.

def signup_step1(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        # 1. 이메일 중복 확인
        if Cust.objects.filter(email=email).exists():
            return render(request, "accounts/signup_step1.html", {"error": "이미 가입된 이메일입니다."})

        # 2. Django 표준 방식으로 비밀번호 암호화 ⭐
        # hashlib.sha256 대신 make_password를 사용합니다.
        # 이 함수는 내부적으로 salt를 추가하고 수천 번 해싱(PBKDF2)하여 매우 안전합니다.
        secure_password = make_password(password)

        # 3. 세션에 안전한 비밀번호 저장
        request.session["reg_email"] = email
        request.session["reg_password"] = secure_password

        return redirect("accounts_app:signup_step2")

    return render(request, "accounts/signup_step1.html")

from django.shortcuts import render, redirect
from django.db import IntegrityError
from .models import Cust, CusProfile  # 필요한 모델 import
import logging  # 로깅 추가 (선택 사항)


# 로거 설정 (선택 사항)
# logger = logging.getLogger(__name__)

def signup_step2(request):
    # ⭐ 수정됨: 아직 DB에 계정이 없으므로 'reg_email' 세션 여부로 유효성 체크
    if not request.session.get("reg_email"):
        return redirect("accounts_app:signup_step1")

    if request.method == "POST":
        # 세션에 입력값만 저장 (DB 저장 안 함)
        request.session["gender"] = request.POST.get("gender")
        request.session["birth_dt"] = request.POST.get("birth_dt", "").replace("-", "")
        request.session["height_cm"] = request.POST.get("height_cm")
        request.session["weight_kg"] = request.POST.get("weight_kg")

        return redirect("accounts_app:signup_step3")

    return render(request, "accounts/signup_step2.html")


def signup_step3(request):
    if not request.session.get("reg_email"):
        return redirect("accounts_app:signup_step1")

    if request.method == "POST":
        # 세션에 선호도 데이터 저장
        request.session["pref_carb"] = request.POST.get("pref_carb", 5)
        request.session["pref_protein"] = request.POST.get("pref_protein", 5)
        request.session["pref_fat"] = request.POST.get("pref_fat", 5)

        request.session["activity_level"] = request.POST.get("activity_level", "1")
        request.session["purpose"] = request.POST.get("purpose", "1")

        return redirect("accounts_app:signup_step4")

    return render(request, "accounts/signup_step3.html")



from django.shortcuts import render, redirect

# from django.contrib.auth.models import User # User 모델을 사용하는 경우
from .models import (
    CusProfile,
    Cust,
)  # Cust 모델과 CusProfile 모델이 import 되어야 합니다.

import logging


# logging.basicConfig(level=logging.INFO) # 필요 시 로깅 설정
from datetime import date

# from .models import CusProfile, Cust # 이 파일에 모델 정의가 필요하다면 import 합니다.

# --- 상수 정의 ---
ACTIVITY_FACTOR = {
    "0": 1.2,  # 활동 적음 (거의 활동 없음)
    "1": 1.375,  # 가벼운 활동 (주 1~3회 운동)
    "2": 1.55,  # 보통 활동 (주 3~5회 운동)
    "3": 1.725,  # 매우 활동적 (매일 운동)
}

OFFSET_MAP = {
    "0": -400,  # 체중 감량
    "1": 0,  # 체중 유지
    "2": 400,  # 체중 증량
}


# --- 계산 함수 정의 ---


def calc_age(birth_dt: str) -> int:
    """생년월일(YYYYMMDD)을 이용해 현재 나이를 계산합니다."""
    # 이제 'YYYYMMDD' 형식임을 가정합니다.
    if not birth_dt or len(birth_dt) != 8 or not birth_dt.isdigit():
        return 0
    try:
        birth = date(int(birth_dt[:4]), int(birth_dt[4:6]), int(birth_dt[6:8]))
        today = date.today()
        return (
            today.year
            - birth.year
            - ((today.month, today.day) < (birth.month, birth.day))
        )
    except ValueError:
        # 날짜 형식이 잘못된 경우 (예: 20000230)
        return 0
    except TypeError:
        # 입력 타입이 잘못된 경우
        return 0


def calc_bmi(weight_kg, height_cm):
    """BMI (체질량 지수)를 계산합니다."""
    # 0으로 나누는 오류 방지
    if height_cm <= 0:
        return 0.0
    height_m = height_cm / 100
    # round(weight_kg / (height_m ** 2), 2)
    return round(weight_kg / (height_m**2), 2)


def calc_bmr(gender, weight, height, age):
    """기초대사량 (BMR)을 해리스-베네딕트 공식으로 계산합니다."""
    # 안전성을 위해 모든 매개변수를 float으로 변환 시도
    try:
        weight = float(weight)
        height = float(height)
        age = int(age)
    except (ValueError, TypeError):
        return 0.0

    if gender == "M":
        # 남성: 66.47 + (13.75 × 체중(kg)) + (5 × 키(cm)) - (6.76 × 나이)
        return round(66.47 + (13.75 * weight) + (5 * height) - (6.76 * age), 2)
    elif gender == "F":
        # 여성: 655.1 + (9.56 × 체중(kg)) + (1.85 × 키(cm)) - (4.68 × 나이)
        return round(655.1 + (9.56 * weight) + (1.85 * height) - (4.68 * age), 2)
    else:
        return 0.0


def calc_tdee(bmr, activity_level):
    """하루 총 소모 칼로리 (TDEE)를 계산합니다."""
    factor = ACTIVITY_FACTOR.get(activity_level, 1.375)  # 기본값 '1'
    return round(bmr * factor, 2)


def calc_recommended_calories(tdee, purpose):
    """권장 섭취 칼로리를 목표(purpose)에 따라 계산합니다."""
    offset = OFFSET_MAP.get(purpose, 0)  # 기본값 0 (유지)
    return tdee + offset, offset


def calc_macro_ratio(carb, protein, fat):
    """탄/단/지 선호도 점수를 비율(%)로 변환합니다."""
    total = carb + protein + fat

    # 합이 0인 경우 (모든 선호도가 0점인 경우) 분모 0 오류 방지
    if total == 0:
        return (33, 34, 33)  # 임의의 기본값 (예: 균형 잡힌 33/34/33)

    return (
        round(carb / total * 100),
        round(protein / total * 100),
        round(fat / total * 100),
    )


# -------------------------------------------------------------------
@transaction.atomic # 계정과 프로필이 둘 다 성공해야만 DB에 반영됨 (원자성)
def signup_step4(request):
    if request.method == "POST":
        # 세션에서 Step 1 데이터 가져오기 (없으면 처음으로 리다이렉트)
        email = request.session.get("reg_email")
        password = request.session.get("reg_password")
        if not email or not password:
            return redirect("accounts_app:signup_step1")

        # 1. Step 4 데이터 추출 (활동량, 목표)
        activity_level = request.POST.get("activity_level", "1")
        purpose = request.POST.get("purpose", "1")

        # 2. 세션에 저장된 이전 단계 데이터 추출 및 클리닝
        try:
            # Step 2에서 저장했을 데이터들
            raw_birth_dt = request.session.get("birth_dt", "").replace("-", "")
            gender = request.session.get("gender", "M")
            height = float(request.session.get("height_cm", 0))
            weight = float(request.session.get("weight_kg", 0))

            # Step 3에서 저장했을 선호도 데이터
            pref_carb = int(request.session.get("pref_carb", 5))
            pref_protein = int(request.session.get("pref_protein", 5))
            pref_fat = int(request.session.get("pref_fat", 5))
        except (ValueError, TypeError) as e:
            print(f"Session data error: {e}")
            return redirect("accounts_app:signup_step2")

        # 3. 계산 로직 (기존 함수들 호출)
        try:
            age = calc_age(raw_birth_dt)
            bmi = calc_bmi(weight, height)
            bmr = calc_bmr(gender, weight, height, age)
            tdee = calc_tdee(bmr, activity_level)
            recommended, offset = calc_recommended_calories(tdee, purpose)
            ratio_c, ratio_p, ratio_f = calc_macro_ratio(pref_carb, pref_protein, pref_fat)

            # 4. 날짜 및 ID 생성
            today_8 = date.today().strftime("%Y%m%d")
            now_14 = timezone.now().strftime("%Y%m%d%H%M%S")
            new_cust_id = generate_new_cust_id()

            # --- [실제 DB 저장 시작] ---
            # A. Cust 계정 생성 (CUST_TM)
            new_user = Cust.objects.create(
                cust_id=new_cust_id,
                email=email,
                password=password,
                created_dt=today_8,
                created_time=now_14,
                updated_time=now_14,
                retry_cnt=0,
                lock_yn='N'
            )

            # B. CusProfile 상세 생성 (CUS_PROFILE_TS)
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
                updated_time=now_14
            )

            # 5. 세션 정리 및 완료
            request.session.flush()
            return redirect("accounts_app:user_login")

        except Exception as e:
            print(f"Final Signup Error: {e}")
            return render(request, "accounts/signup_step4.html", {"error": f"가입 처리 중 오류 발생: {e}"})

    return render(request, "accounts/signup_step4.html")

from django.contrib.auth import authenticate, login
from django.shortcuts import redirect
from django.contrib import messages

def test_login_view(request):
    # 1. 테스트 계정 정보 설정 (DB에 이미 해당 정보가 있어야 합니다)
    test_email = "test@test"
    test_password = "11111111"

    # 2. 사용자 인증 (Django 기본 auth를 사용하는 경우 기준)
    # 만약 Cust 모델을 커스텀하여 사용 중이라면 해당 모델에 맞춰 인증 로직을 조정하세요.
    user = authenticate(request, username=test_email, password=test_password)

    if user is not None:
        # 3. 인증 성공 시 세션 로그인 처리
        login(request, user)
        # 4. 'home' 페이지로 이동 (urls.py에 정의된 name='home' 기준)
        return redirect('home')
    else:
        # 5. 테스트 계정이 DB에 없을 경우 에러 메시지와 함께 로그인 페이지로 리다이렉트
        messages.error(request, "테스트 계정이 존재하지 않습니다. 관리자에게 문의하세요.")
        return redirect('accounts_app:user_login')

# accounts/views.py
from django.contrib.auth.decorators import login_required

@login_required(login_url='accounts_app:user_login')
def profile(request):
    # 로그인된 사용자는 request.user에 담겨 있습니다.
    # 만약 여기서 오류가 난다면 로그인이 풀린 것입니다.
    return render(request, "accounts/profile.html", {"user": request.user})