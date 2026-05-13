# P0 A3 Infra/DB/Prod 验收说明

生成日期：2026-05-13

## 范围

A3 负责 P0.3、P0.4、P0.5：

- Docker server / daemon 镜像和 `docker-compose.yml` 验证路径。
- PostgreSQL migrate 和 pytest 验证路径。
- `settings_prod`、Redis、SMTP、Sentry、structlog、nginx、health 配置完善。

## 本地自动化验收

在 `bodiagent/` 目录执行：

```bash
docker compose build
docker compose up -d db redis web
docker compose ps
curl -fsS http://127.0.0.1:8000/health/
docker compose exec web python manage.py migrate --check
docker compose exec web python manage.py collectstatic --noinput --dry-run
docker compose exec web pytest -n auto
docker compose --profile daemon run --rm daemon status
```

预期结果：

- `db`、`redis`、`web` 均为 healthy。
- `/health/` 返回 `OK`。
- PostgreSQL 下 migrations 已应用。
- `collectstatic` 可重复运行。
- pytest 在 PostgreSQL 配置下通过；若其他 AGENT 正在修改业务逻辑，记录失败用例和提交时间。
- daemon 镜像可启动并读取容器环境；真实任务执行由 A4 验证。

## 生产配置验收

生产部署前需要提供：

- `DJANGO_SECRET_KEY`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `POSTGRES_*`
- `REDIS_URL`
- SMTP 凭据或明确使用 console backend 的测试环境
- 可选 `SENTRY_DSN`

无真实 SMTP/Sentry 凭据时，本地替代验收：

```bash
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend docker compose up -d web
SENTRY_DSN= docker compose up -d web
```

真实凭据到位后的人工验收：

- 触发一封注册/验证邮件，确认 SMTP 送达。
- 临时触发并捕获一个测试异常，确认 Sentry 收到事件。
- 通过 nginx 访问 `/health/`、普通 HTTP 页面和 `/ws/` WebSocket 升级路径。

## nginx

示例配置在 `docker/nginx.conf`，覆盖：

- `/health/` 代理。
- `/static/` 和 `/media/` 由 nginx 直接服务。
- `/ws/` WebSocket 升级头。
- `X-Forwarded-Proto`，配合 Django `SECURE_PROXY_SSL_HEADER`。

## 外部阻塞

- 镜像推送需要 registry 凭据。
- SMTP、Sentry 真实验收需要外部服务凭据。
- daemon 真实 AI CLI 链路需要 A4 提供 token、workspace 和本机 CLI 凭据。
