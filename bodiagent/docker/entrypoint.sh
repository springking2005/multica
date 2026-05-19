#!/bin/sh
set -eu

if [ "${DJANGO_WAIT_FOR_DB:-1}" = "1" ]; then
  python - <<'PY'
import os
import sys
import time

import psycopg

deadline = time.time() + int(os.environ.get("DJANGO_DB_WAIT_TIMEOUT", "60"))
dsn = {
    "dbname": os.environ.get("POSTGRES_DB", "bodiagent"),
    "user": os.environ.get("POSTGRES_USER", "bodiagent"),
    "password": os.environ.get("POSTGRES_PASSWORD", ""),
    "host": os.environ.get("POSTGRES_HOST", "db"),
    "port": os.environ.get("POSTGRES_PORT", "5432"),
}

while True:
    try:
        with psycopg.connect(**dsn):
            break
    except Exception as exc:
        if time.time() >= deadline:
            print(f"database unavailable after wait: {exc}", file=sys.stderr)
            raise
        time.sleep(1)
PY
fi

if [ "${DJANGO_MIGRATE_ON_START:-1}" = "1" ]; then
  python manage.py migrate --noinput
fi

if [ "${DJANGO_COLLECTSTATIC_ON_START:-1}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

if [ -n "${BODIAGENT_BOOTSTRAP_ADMIN_EMAIL:-}" ] || [ -n "${BODIAGENT_BOOTSTRAP_ADMIN_PASSWORD:-}" ]; then
  if [ -z "${BODIAGENT_BOOTSTRAP_ADMIN_EMAIL:-}" ] || [ -z "${BODIAGENT_BOOTSTRAP_ADMIN_PASSWORD:-}" ]; then
    echo "BODIAGENT_BOOTSTRAP_ADMIN_EMAIL and BODIAGENT_BOOTSTRAP_ADMIN_PASSWORD must be set together" >&2
    exit 1
  fi
  if [ "${BODIAGENT_BOOTSTRAP_ADMIN_UPDATE_PASSWORD:-1}" = "0" ] || [ "${BODIAGENT_BOOTSTRAP_ADMIN_UPDATE_PASSWORD:-1}" = "false" ]; then
    python manage.py bootstrap_admin --email "$BODIAGENT_BOOTSTRAP_ADMIN_EMAIL" --password "$BODIAGENT_BOOTSTRAP_ADMIN_PASSWORD" --name "${BODIAGENT_BOOTSTRAP_ADMIN_NAME:-admin}" --preserve-password
  else
    python manage.py bootstrap_admin --email "$BODIAGENT_BOOTSTRAP_ADMIN_EMAIL" --password "$BODIAGENT_BOOTSTRAP_ADMIN_PASSWORD" --name "${BODIAGENT_BOOTSTRAP_ADMIN_NAME:-admin}"
  fi
fi

exec "$@"
