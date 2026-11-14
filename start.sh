#!/bin/sh
set -eu

mkdir -p "${DATA_DIR:-/data}/media"
if [ -z "${DJANGO_SECRET_KEY:-}" ]; then
  secret_file="${DATA_DIR:-/data}/.django-secret-key"
  if [ ! -s "$secret_file" ]; then
    python -c 'import secrets; print(secrets.token_urlsafe(64))' > "$secret_file"
    chmod 600 "$secret_file"
  fi
  DJANGO_SECRET_KEY="$(cat "$secret_file")"
  export DJANGO_SECRET_KEY
fi
python manage.py migrate --noinput
python deploy/ensure_superuser.py
python manage.py collectstatic --noinput

exec gunicorn b2b.wsgi:application \
  --bind "0.0.0.0:${PORT:-7860}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout 120
