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

exec "$@"
