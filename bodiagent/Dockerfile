# Production Docker image for BodiAgent server.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=bodiagent.settings_prod \
    STATIC_ROOT=/app/staticfiles \
    MEDIA_ROOT=/app/data/uploads

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates git libpq5 netcat-openbsd && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -c 'import tomllib; data = tomllib.load(open("pyproject.toml", "rb")); deps = data["project"]["dependencies"] + ["gunicorn", "uvicorn"]; open("/tmp/requirements.txt", "w").write("\n".join(deps) + "\n")' \
    && pip install --no-cache-dir -r /tmp/requirements.txt

COPY . .

RUN pip install --no-cache-dir --no-build-isolation --no-deps . \
    && chmod +x /app/docker/entrypoint.sh \
    && mkdir -p /app/staticfiles /app/data/uploads \
    && addgroup --system bodiagent \
    && adduser --system --ingroup bodiagent --home /home/bodiagent bodiagent \
    && chown -R bodiagent:bodiagent /app /home/bodiagent

USER bodiagent

EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=3).read()"
CMD ["sh", "-c", "exec gunicorn bodiagent.asgi:application -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 -w ${WEB_CONCURRENCY:-2}"]
