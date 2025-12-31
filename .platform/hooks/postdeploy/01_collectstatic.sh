#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/var/app/current/Projects"
ENV_FILE="/opt/elasticbeanstalk/deployment/env"
PY="/var/app/venv/staging-LQM1lest/bin/python"

echo "[postdeploy] collectstatic start"
echo "[postdeploy] APP_DIR=$APP_DIR"
echo "[postdeploy] ENV_FILE=$ENV_FILE"
echo "[postdeploy] PY=$PY"

# 1) 경로/파일 존재 확인
if [ ! -d "$APP_DIR" ]; then
  echo "[postdeploy] ERROR: APP_DIR not found: $APP_DIR"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "[postdeploy] ERROR: ENV_FILE not found: $ENV_FILE"
  exit 1
fi

if [ ! -x "$PY" ]; then
  echo "[postdeploy] ERROR: python not executable: $PY"
  exit 1
fi

cd "$APP_DIR"

# 2) EB env 파일을 안전하게 주입해서 collectstatic 실행
#    - source 금지(특수문자 깨짐)
#    - env -i 로 깨끗한 환경에서 key=value들만 주입
sudo /usr/bin/env -i \
  $(sudo /bin/cat "$ENV_FILE" | /usr/bin/tr '\n' ' ') \
  "$PY" manage.py collectstatic --noinput

echo "[postdeploy] collectstatic done"
