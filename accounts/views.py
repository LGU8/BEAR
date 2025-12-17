from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect
from django.utils import timezone
from django.db.models import Max
from .models import Cust, LoginHistory, CusProfile
import hashlib
from django.contrib.auth.models import User
from datetime import date
import hashlib # ⭐ 이 라인을 추가합니다.
from django.shortcuts import render, redirect

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.conf import settings  # settings.LOGIN_REDIRECT_URL 사용을 위해 필요

# settings.py에 LOGIN_REDIRECT_URL = 'profile' 설정을 추가했다고 가정

# cust_id를 생성하는 도우미 함수 (cust_id가 VARCHAR이므로 문자열로 처리)
def generate_new_cust_id():
    """현재 DB의 최대 cust_id를 찾아 1 증가시킨 새 ID를 반환 (VARCHAR 처리)"""
    # 현재 cust_id의 최댓값을 가져옵니다.
    # Cust.objects.all()에서 Max를 사용해야 합니다.
    max_id_str = Cust.objects.all().aggregate(Max('cust_id'))['cust_id__max']

    if max_id_str:
        # 문자열을 숫자로 변환 후 1 증가
        new_id_int = int(max_id_str) + 1
        # 다시 VARCHAR(10)에 맞게 문자열로 포맷팅 (예: 0000000001, 0000000010 등)
        # cust_id가 10자리 문자열이라고 가정하고, 0으로 채웁니다.
        # 실제 데이터 포맷에 따라 이 부분이 달라질 수 있습니다.
        new_cust_id = str(new_id_int).zfill(10)
    else:
        # 테이블이 비어있으면 1번 ID (0000000001)부터 시작
        new_cust_id = '0000000001'

    return new_cust_id


# 1. 로그인 뷰 (GET 요청: 폼 표시, POST 요청: 인증 처리)
# accounts/views.py - user_login 함수

def user_login(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        # authenticate가 CustomCustBackend를 통해 Cust 객체를 반환합니다.
        user = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)  # 세션 생성

            # last_login_dt 업데이트 (이전 답변에서 CHAR(14)로 확장됨)
            user.last_login_dt = timezone.now().strftime('%Y%m%d%H%M%S')
            user.save()

            # LoginHistory 기록 (timezone.now() import 필요)
            try:
                  # LoginHistory 모델 import 필요
                LoginHistory.objects.create(
                    cust=user,
                    login_dt=timezone.now().strftime('%Y%m%d'),  # 날짜
                    login_time=timezone.now().strftime('%Y%m%d%H%M%S'),  # 시간
                    success_yn='Y'
                )
            except Exception as e:
                print(f"LoginHistory save error: {e}")

            return redirect('profile')
        else:
            return render(request, 'accounts/login.html', {'error_message': '이메일 또는 비밀번호가 올바르지 않습니다.'})

    return render(request, 'accounts/login.html')

# 2. 로그아웃 뷰
def user_logout(request):
    # 1. Cust 테이블의 leave_dt 필드 업데이트
    # 사용자가 로그인 상태인지 확인합니다. (request.user는 로그인된 사용자 객체입니다.)
    if request.user.is_authenticated:
        try:
            # request.user가 Cust 모델의 인스턴스라 가정하거나,
            # Cust 테이블의 필드를 업데이트할 수 있는 객체라 가정합니다.

            # 현재 시간을 DB 필드 형식에 맞춰 포맷팅합니다.
            # (예: YYYYMMDDHHMMSS 또는 YYYY-MM-DD HH:MM:SS)
            # 여기서는 예시로 'YYYYMMDDHHMMSS' 형식을 사용합니다.
            current_dt = timezone.now().strftime('%Y%m%d%H%M%S')

            # Cust 객체를 직접 업데이트하거나, request.user가 Cust라면 바로 업데이트
            # request.user가 Cust 객체라고 가정하고 진행합니다.
            request.user.leave_dt = current_dt
            request.user.save()

            print(f"User {request.user.email} logged out at {current_dt}")

        except AttributeError:
            # request.user에 leave_dt 필드가 없거나 Cust 객체가 아닌 경우
            print("Error: request.user does not have 'leave_dt' field or is not Cust model.")
        except Exception as e:
            print(f"Error updating leave_dt: {e}")

    # 2. Django 세션에서 사용자 정보 제거 (실제 로그아웃 처리)
    logout(request)

    # 3. 로그아웃 후 홈 또는 로그인 페이지로 이동
    return redirect('home')


# 3. 프로필 뷰 (로그인 필요)
@login_required
def profile(request):
    # 로그인된 사용자 정보가 request.user에 담겨 템플릿으로 전달됨
    return render(request, 'accounts/profile.html', {'user': request.user})


# 4. 홈 뷰 (제공해주신 home.html을 렌더링)
def home(request):
    return render(request, 'accounts/home.html')

import secrets
import string

def password_reset():
    return ''.join(secrets.choice(
        string.ascii_letters + string.digits
    ) for _ in range(10))



import hashlib
from datetime import date
from django.shortcuts import render, redirect
# from django.utils import timezone # created_dt를 오늘 날짜로 단순화하여 사용하지 않음
from django.db import IntegrityError # DB 에러 처리를 위해 추가
from .models import Cust, CusProfile # 모델 import 확인


def signup_step1(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        # 1. 이메일 중복 확인
        if Cust.objects.filter(email=email).exists():
            return render(request, 'accounts/signup_step1.html', {
                'error': '이미 가입된 이메일입니다.'
            })

        # 2. 비밀번호 해시
        # Django의 make_password가 아닌, 기존 로직에 맞게 hashlib 사용
        hashed_password = hashlib.sha256(password.encode('utf-8')).hexdigest()

        # 3. 오늘 날짜 포맷 (YYYYMMDD)
        today = date.today().strftime('%Y%m%d')
        new_cust_id = generate_new_cust_id()  # 고유 ID 생성
        try:
            # 4. Cust 및 CusProfile 생성
            cust = Cust.objects.create(
                cust_id=new_cust_id,  # ⭐ 생성된 ID 값 전달 ⭐
                email=email,
                password=hashed_password,
                created_dt=today
            )

            # Cust 생성과 동시에 프로필 테이블도 생성
            CusProfile.objects.create(cust=cust)

            # 5. 세션에 ID 저장 및 다음 단계로 이동
            request.session['cust_id'] = cust.cust_id
            return redirect('signup_step2')

        except IntegrityError as e:
            # DB 무결성 에러 (예: 이메일 unique 제약조건 위반 등)
            print(f"DB Integrity Error in Step 1: {e}")
            return render(request, 'accounts/signup_step1.html', {
                'error': '회원가입 처리 중 데이터베이스 오류가 발생했습니다.'
            })
        except Exception as e:
            print(f"General Error in Step 1: {e}")
            return render(request, 'accounts/signup_step1.html', {
                'error': '알 수 없는 오류가 발생했습니다.'
            })

    return render(request, 'accounts/signup_step1.html')


from django.shortcuts import render, redirect
from django.db import IntegrityError
from .models import Cust, CusProfile  # 필요한 모델 import
import logging  # 로깅 추가 (선택 사항)


# 로거 설정 (선택 사항)
# logger = logging.getLogger(__name__)

def signup_step2(request):
    cust_id = request.session.get('cust_id')

    # 세션 검증: cust_id가 없으면 Step 1로 리다이렉트
    if not cust_id:
        # logger.warning("Step 2 accessed without cust_id in session.")
        return redirect('signup_step1')

    if request.method == "POST":

        # POST 데이터 추출
        raw_birth_dt = request.POST.get('birth_dt')
        gender = request.POST.get('gender')
        height_cm = request.POST.get('height_cm')
        weight_kg = request.POST.get('weight_kg')

        try:
            # 1. Cust ID로 CusProfile 객체 가져오기
            # cust_id는 문자열이지만, CusProfile의 cust_id는 외래키(BIGINT/VARCHAR)입니다.
            # ORM이 타입 변환을 처리하지만, 객체가 없으면 DoesNotExist 발생.
            profile = CusProfile.objects.get(cust_id=cust_id)

            # 2. birth_dt 클리닝: YYYY-MM-DD (10자)를 YYYYMMDD (8자)로 변환
            if raw_birth_dt and '-' in raw_birth_dt:
                birth_dt_cleaned = raw_birth_dt.replace('-', '')
            else:
                # None 또는 이미 8자 형태인 경우
                birth_dt_cleaned = raw_birth_dt

                # 3. 프로필 필드 업데이트 (DB 저장)
            profile.gender = gender
            profile.birth_dt = birth_dt_cleaned
            profile.height_cm = height_cm
            profile.weight_kg = weight_kg
            profile.save()

            # ⭐ 4. Step 4에서 사용하도록 세션에 저장 (계산에 필요한 원시 데이터) ⭐
            # DB에 저장한 값을 그대로 세션에 저장하여 Step 4에서 사용
            request.session['gender'] = profile.gender
            request.session['birth_dt'] = profile.birth_dt
            request.session['height_cm'] = profile.height_cm
            request.session['weight_kg'] = profile.weight_kg

            # 5. 다음 단계로 이동
            return redirect('signup_step3')

        except CusProfile.DoesNotExist:
            # Step 1에서 cust_id가 생성되었으나, CusProfile 생성이 누락된 경우
            # logger.error(f"CusProfile missing for cust_id: {cust_id}")
            return redirect('signup_step1')  # 다시 처음부터 시작하도록 유도

        except Exception as e:
            # 기타 예외 (DB 오류, 타입 변환 오류 등)
            # logger.error(f"Error in Step 2 POST for cust_id {cust_id}: {e}")

            # 오류 메시지와 함께 Step 2 폼을 다시 렌더링
            return render(request, 'accounts/signup_step2.html', {
                'error': '입력 값 처리 중 오류가 발생했습니다. 모든 필드를 올바르게 입력했는지 확인해주세요.'
            })

    # GET 요청 처리 (폼 렌더링)
    return render(request, 'accounts/signup_step2.html')


def signup_step3(request):
    cust_id = request.session.get('cust_id')
    if not cust_id:
        return redirect('signup_step1')

    if request.method == "POST":
        request.session['pref_carb'] = request.POST.get('pref_carb')
        request.session['pref_protein'] = request.POST.get('pref_protein')
        request.session['pref_fat'] = request.POST.get('pref_fat')

        request.session['activity_level'] = request.POST.get('activity_level')
        request.session['purpose'] = request.POST.get('purpose')

        return redirect('signup_step4')

    return render(request, 'accounts/signup_step3.html')


from django.shortcuts import render, redirect
# from django.contrib.auth.models import User # User 모델을 사용하는 경우
from .models import CusProfile, Cust  # Cust 모델과 CusProfile 모델이 import 되어야 합니다.

import logging


# logging.basicConfig(level=logging.INFO) # 필요 시 로깅 설정
from datetime import date

# from .models import CusProfile, Cust # 이 파일에 모델 정의가 필요하다면 import 합니다.

# --- 상수 정의 ---
ACTIVITY_FACTOR = {
    '0': 1.2,  # 활동 적음 (거의 활동 없음)
    '1': 1.375,  # 가벼운 활동 (주 1~3회 운동)
    '2': 1.55,  # 보통 활동 (주 3~5회 운동)
    '3': 1.725,  # 매우 활동적 (매일 운동)
}

OFFSET_MAP = {
    '0': -400,  # 체중 감량
    '1': 0,  # 체중 유지
    '2': 400,  # 체중 증량
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
        return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
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
    return round(weight_kg / (height_m ** 2), 2)


def calc_bmr(gender, weight, height, age):
    """기초대사량 (BMR)을 해리스-베네딕트 공식으로 계산합니다."""
    # 안전성을 위해 모든 매개변수를 float으로 변환 시도
    try:
        weight = float(weight)
        height = float(height)
        age = int(age)
    except (ValueError, TypeError):
        return 0.0

    if gender == 'M':
        # 남성: 66.47 + (13.75 × 체중(kg)) + (5 × 키(cm)) - (6.76 × 나이)
        return round(66.47 + (13.75 * weight) + (5 * height) - (6.76 * age), 2)
    elif gender == 'F':
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
def signup_step4(request):
    if request.method == 'POST':
        cust_id = request.session.get('cust_id')
        if not cust_id:
            return redirect('signup_step1')

        # 1. Step 4 POST 데이터 세션 저장 (활동량, 목표)
        request.session['activity_level'] = request.POST.get('activity_level')
        request.session['purpose'] = request.POST.get('purpose')

        # ⭐ 2. 비율 데이터 추출 및 클리닝 (ValueError 발생 가능성 가장 높은 곳)
        try:
            # 세션에서 값을 가져오고 int()로 변환. 실패하면 5점을 기본값으로 사용
            pref_carb = int(request.session.get('pref_carb', 5))
            pref_protein = int(request.session.get('pref_protein', 5))
            pref_fat = int(request.session.get('pref_fat', 5))
        except ValueError as ve:
            # '2-'와 같은 유효하지 않은 값이 세션에 저장되어 변환 실패 시:
            print(f"Error: Corrupt preference data in session: {ve}")
            # 안전하게 기본값 5/5/5로 설정하여 계산 진행을 보장
            pref_carb = 5
            pref_protein = 5
            pref_fat = 5

        # 3. 메인 계산 및 DB 저장 로직 (Cust.DoesNotExist 등 기타 에러는 여기서 발생)
        try:
            cust = Cust.objects.get(cust_id=cust_id)

            # --- 필수 세션 데이터 추출 (NoneType 방지) ---
            gender = request.session.get('gender')
            raw_birth_dt = request.session.get('birth_dt')

            # ⭐ 날짜 형식 클리닝: 'YYYY-MM-DD' (10자)를 'YYYYMMDD' (8자)로 변환
            if raw_birth_dt and '-' in raw_birth_dt:
                birth_dt = raw_birth_dt.replace('-', '')  # 하이픈 제거
            else:
                birth_dt = raw_birth_dt  # 이미 8자 형태거나 None인 경우 그대로 사용

            # float 변환
            height = float(request.session.get('height_cm', 0))
            weight = float(request.session.get('weight_kg', 0))

            activity_level = request.session.get('activity_level', '1')
            purpose = request.session.get('purpose', '1')

            # --- 계산 ---
            # birth_dt이 None이거나 형식 오류일 경우 calc_age에서 에러가 발생할 수 있습니다.
            age = calc_age(birth_dt)
            bmi = calc_bmi(weight, height)
            bmr = calc_bmr(gender, weight, height, age)
            tdee = calc_tdee(bmr, activity_level)
            recommended, offset = calc_recommended_calories(tdee, purpose)

            ratio_c, ratio_p, ratio_f = calc_macro_ratio(pref_carb, pref_protein, pref_fat)

            # --- DB 저장 ---
            profile, created = CusProfile.objects.update_or_create(
                cust=cust,
                defaults={
                    'height_cm': height, 'weight_kg': weight, 'bmi': bmi, 'bmr': bmr,
                    'gender': gender, 'birth_dt': birth_dt,
                    'ratio_carb': ratio_c, 'ratio_protein': ratio_p, 'ratio_fat': ratio_f,
                    'activity_level': activity_level, 'purpose': purpose,
                    'calories_burned': tdee, 'recommended_calories': recommended,
                    'offset': offset,
                }
            )

            request.session.flush()
            return redirect('profile')

        except Exception as e:
            # Cust.DoesNotExist, calc_age 오류, DB 저장 오류 등 기타 오류
            print(f"Error in signup_step4 (General Exception): {e}")
            # 오류가 발생하면 Step 3로 리다이렉트
            return redirect('signup_step3')

    return render(request, 'accounts/signup_step4.html')



# GET 요청에 대한 렌더링은 그대로 유지
# return render(request, 'accounts/signup_step4.html')


def home(request):
    """
    첫 진입 화면
    - 로그인
    - 회원가입 버튼만 표시
    """
    return render(request, 'accounts/home.html')

