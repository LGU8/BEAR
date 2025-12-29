from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.hashers import check_password
from .models import Cust


class CustBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # username 자리에 email이 들어옵니다.
        email = username
        try:
            # 1. 우리 모델(Cust)에서 이메일로 사용자 찾기
            user = Cust.objects.get(email=email)

            # 2. 암호화된 비밀번호와 입력된 비밀번호 비교
            if check_password(password, user.password):
                return user
        except Cust.DoesNotExist:
            return None

    def get_user(self, user_id):
        try:
            return Cust.objects.get(pk=user_id)
        except Cust.DoesNotExist:
            return None
        
# import hashlib
# from django.contrib.auth.backends import ModelBackend
# from .models import Cust  # 너희 프로젝트에서 실제 로그인 모델명에 맞춰 유지

# class CustBackend(ModelBackend):
#     def authenticate(self, request, username=None, password=None, **kwargs):
#         email = (username or "").strip()
#         raw_pw = (password or "").strip()
#         if not email or not raw_pw:
#             return None

#         try:
#             user = Cust.objects.get(email=email)

#             # 잠금 계정 차단(선택이지만 강추)
#             if (getattr(user, "lock_yn", "N") or "N").strip() == "Y":
#                 return None

#             input_hash = hashlib.sha256(raw_pw.encode("utf-8")).hexdigest()
#             db_hash = (user.password or "").strip()

#             if input_hash == db_hash:
#                 return user

#             return None
#         except Cust.DoesNotExist:
#             return None

#     def get_user(self, user_id):
#         try:
#             return Cust.objects.get(pk=user_id)
#         except Cust.DoesNotExist:
#             return None