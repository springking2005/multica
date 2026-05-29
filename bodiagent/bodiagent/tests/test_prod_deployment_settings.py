import importlib
import sys
from pathlib import Path


def _reload_prod_settings(monkeypatch, **env):
    module_name = "bodiagent.settings_prod"
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ALLOWED_HOSTS", "106.53.153.76,localhost")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_http_direct_deploy_can_disable_secure_cookies_with_ssl_redirect(monkeypatch):
    settings = _reload_prod_settings(monkeypatch, SECURE_SSL_REDIRECT="false")

    assert settings.SECURE_SSL_REDIRECT is False
    assert settings.SESSION_COOKIE_SECURE is False
    assert settings.CSRF_COOKIE_SECURE is False
    assert settings.SECURE_HSTS_SECONDS == 0


def test_https_deploy_keeps_secure_cookies_by_default(monkeypatch):
    settings = _reload_prod_settings(monkeypatch, SECURE_SSL_REDIRECT="true")

    assert settings.SECURE_SSL_REDIRECT is True
    assert settings.SESSION_COOKIE_SECURE is True
    assert settings.CSRF_COOKIE_SECURE is True
    assert settings.SECURE_HSTS_SECONDS == 31536000


def test_asgi_serves_static_assets_by_default_in_prod(monkeypatch):
    settings = _reload_prod_settings(monkeypatch, SECURE_SSL_REDIRECT="false")

    assert settings.BODIAGENT_SERVE_STATIC is True



def test_prod_asgi_wraps_http_app_with_static_handler(monkeypatch):
    import os
    import subprocess

    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "bodiagent.settings_prod",
        "DJANGO_SECRET_KEY": "test-secret",
        "ALLOWED_HOSTS": "106.53.153.76,localhost",
        "REDIS_URL": "redis://localhost:6379/0",
        "SECURE_SSL_REDIRECT": "false",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import bodiagent.asgi as a; print(a.django_asgi_app.__class__.__name__)",
        ],
        check=True,
        cwd=os.getcwd(),
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.stdout.strip() == "ASGIStaticFilesHandler"


def test_prod_disables_persistent_db_connections_by_default(monkeypatch):
    settings = _reload_prod_settings(monkeypatch)

    assert settings.DATABASES["default"]["CONN_MAX_AGE"] == 0


def test_prod_allows_explicit_persistent_db_connections(monkeypatch):
    settings = _reload_prod_settings(monkeypatch, DB_CONN_MAX_AGE="30")

    assert settings.DATABASES["default"]["CONN_MAX_AGE"] == 30


def test_docker_runtime_exposes_connection_pressure_knobs():
    dockerfile = Path("Dockerfile").read_text()
    compose = Path("docker-compose.yml").read_text()
    env_example = Path(".env.example").read_text()

    assert "${WEB_CONCURRENCY:-2}" in dockerfile
    assert "DB_CONN_MAX_AGE: ${DB_CONN_MAX_AGE:-0}" in compose
    assert "WEB_CONCURRENCY: ${WEB_CONCURRENCY:-2}" in compose
    assert "DB_CONN_MAX_AGE=0" in env_example
    assert "WEB_CONCURRENCY=2" in env_example


def test_dockerfile_installs_server_dependencies_before_source_copy():
    dockerfile = Path("Dockerfile").read_text()

    assert dockerfile.index("COPY pyproject.toml ./") < dockerfile.index("COPY . .")
    assert "pip install --no-cache-dir -r /tmp/requirements.txt" in dockerfile
    assert "pip install --no-cache-dir --no-build-isolation --no-deps ." in dockerfile


def test_daemon_dockerfile_installs_dependencies_before_source_copy():
    dockerfile = Path("Dockerfile.daemon").read_text()

    assert dockerfile.index("COPY daemon_cli/pyproject.toml") < dockerfile.index("COPY daemon_cli /app/daemon_cli")
    assert "pip install --no-cache-dir -r /tmp/daemon-requirements.txt" in dockerfile
    assert "pip install --no-cache-dir --no-build-isolation --no-deps -e /app/daemon_cli" in dockerfile


def test_env_example_does_not_pin_secure_cookie_flags():
    env_example = Path(".env.example").read_text()

    assert "SESSION_COOKIE_SECURE=" not in env_example
    assert "CSRF_COOKIE_SECURE=" not in env_example
    assert "SESSION/CSRF cookie security follows this setting" in env_example
