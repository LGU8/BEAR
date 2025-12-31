#!/bin/bash
set -e

APP_DIR="/var/app/current/Projects"
VENV_PY="/var/app/venv/staging-LQM1lest/bin/python"
ENVFILE="/opt/elasticbeanstalk/deployment/env"
TMP_EXPORT="/tmp/eb_export_collectstatic.sh"

cd "$APP_DIR"

# EB env 파일은 source로 깨질 수 있으니, 필요한 키만 '단일 인용부호'로 감싸 export 생성
sudo egrep "^(DJANGO_SETTINGS_MODULE|SECRET_KEY|DB_HOST|DB_NAME|DB_USER|DB_PASSWORD|DB_PORT|ALLOWED_HOSTS)=" "$ENVFILE" \
| sed -E "s/^([A-Z0-9_]+)=(.*)$/export \1='\''\2'\''/g" \
> "$TMP_EXPORT"

set -a
source "$TMP_EXPORT"
set +a

"$VENV_PY" manage.py collectstatic --noinput
