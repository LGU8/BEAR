#!/usr/bin/env bash
set -euo pipefail

cd /var/app/current

# EB env 로드(중요)
if [ -f /opt/elasticbeanstalk/deployment/env ]; then
  set -a
  source /opt/elasticbeanstalk/deployment/env
  set +a
fi

# venv python 찾기(디렉토리명은 staging-XXXX 형태라 와일드카드)
PY="$(ls -1d /var/app/venv/*/bin/python | head -n 1)"

# 1회 처리(여러 건 처리하고 싶으면 --once 빼고 --limit 조절)
"$PY" /var/app/current/manage.py ocr_worker --limit 5
