import os
import sys

# Django 프로젝트가 Projects/ 아래에 있으니 Python path에 추가
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(BASE_DIR, "Projects")
if PROJECTS_DIR not in sys.path:
    sys.path.insert(0, PROJECTS_DIR)

# Django settings 지정
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conf.settings")

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
