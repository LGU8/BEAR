# conf/middleware.py
from django.shortcuts import redirect
from django.http import HttpResponseForbidden


class DemoModeBlockMiddleware:
    """
    Demo Mode에서:
    - settings: badges만 허용
    - record: 전부 차단(우선 보수적으로)
    - timeline/badges/report/home은 허용
    """

    def __init__(self, get_response):
        self.get_response = get_response

        self.allow_prefixes = (
            "/home/",
            "/report/",
            "/timeline/",
            "/badges/",
            "/settings/badges/",
            "/accounts/logout/",
            "/accounts/login/",
            "/accounts/demo/",     # demo 진입/확장 대비
            "/static/",
            "/media/",
            "/admin/",             # 운영 편의(원치 않으면 제거)
        )

    def __call__(self, request):
        is_demo = bool(request.session.get("is_demo"))
        if not is_demo:
            return self.get_response(request)

        path = request.path

        # 1) 허용 경로는 통과
        if path.startswith(self.allow_prefixes):
            return self.get_response(request)

        # 2) settings: badges 외 전부 차단
        if path.startswith("/settings/"):
            return redirect("report_app:report_daily")

        # 3) record: 전부 차단(쓰기/스캔/카메라/API 포함)
        if path.startswith("/record/"):
            # 강차단: write method면 403(명확)
            if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                return HttpResponseForbidden("Demo mode: write operations are blocked.")
            # GET이라도 record 자체는 체험 범위에서 제외(리포트/타임라인으로 유도)
            return redirect("report_app:report_daily")

        # 4) 나머지 예측불가 경로는 안전하게 report로 유도
        return redirect("report_app:report_daily")
