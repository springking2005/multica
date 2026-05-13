# BodiAgent P0 五 AGENT 并行执行规划

> 生成日期：2026-05-13  
> 基准文档：`bodiagent/docs/后续开发路线图.md`  
> 执行策略：资源有限，按 5 个 AGENT 启动；优先完成 P0 阻塞投产项。

## 结论

本轮采用 **5 个 AGENT 并行**：

1. **A1 Realtime/Chat**：WebSocket 路由、Chat smoke test、Chat UI。
2. **A2 Frontend CRUD**：Agent、Project、Autopilot、CLI Token 等 Django Templates + HTMX 页面。
3. **A3 Infra/DB/Prod**：Docker、PostgreSQL 迁移验证、生产配置。
4. **A4 Daemon E2E**：daemon_cli 端到端验证和可重复测试脚本。
5. **A5 Integration/QA**：集成验收、测试矩阵、冲突协调、文档同步。

不建议超过 5 个起步。P0 涉及较多共享文件，如 `settings*.py`、`urls.py`、`asgi.py`、模板布局、Docker 配置和测试配置；继续加人会显著增加合并冲突和重复返工。

## 路线图修正项

原路线图整体可执行，但启动前记录以下修正，作为本轮执行基线：

- P0 实际包含 **6 项**：P0.0 到 P0.5。
- P0 总工作量按条目相加为 **20.75 人天**，不是汇总表中的 19.75 人天。
- P0.2 daemon E2E 的前置依赖应为 **P0.3 Docker/Redis 环境**、**P0.4 PostgreSQL 验证**，以及至少一个真实或可替代的 AI CLI 执行环境。
- 外部服务类验收，如 SMTP、Sentry、真实 AI CLI、镜像推送，应拆分为“本地可验证能力”和“凭据到位后的人工验收”。

## AGENT 分工

### A1 Realtime/Chat

负责范围：

- P0.0 WebSocket 路由注册与 smoke test。
- P0.1 中的 Chat UI。
- Chat 前端 WebSocket JavaScript 集成。

建议写入范围：

- `bodiagent/bodiagent/asgi.py`
- `bodiagent/chat/`
- `bodiagent/frontend/templates/` 中与 Chat 直接相关的模板
- Chat 相关测试文件

避免修改：

- Docker、生产 settings、daemon_cli。
- 与 Chat 无关的全局模板结构，除非先与 A2/A5 对齐。

必须覆盖的场景：

- WebSocket 可连接 `/ws/chat/{session_id}/`。
- 两个客户端加入同一 session 后可广播消息。
- 未登录、无权限 session、非法 UUID、断线重连或断开处理。
- Chat UI 对用户输入进行 HTML 转义，避免 XSS。
- Chat UI 在 375px 宽度下可用。

### A2 Frontend CRUD

负责范围：

- P0.1 中除 Chat UI 之外的核心前端模板。
- Agent 创建、编辑、删除、配置入口。
- Project 创建、编辑、列表、删除。
- Autopilot 创建、编辑、列表、删除。
- Token / CLI Token 管理页。

建议写入范围：

- `bodiagent/frontend/templates/`
- `bodiagent/bodiagent/views_frontend.py`
- `bodiagent/bodiagent/urls.py`
- 对应 app 的 view 层和前端测试

避免修改：

- `chat/consumers.py`、`asgi.py` 中 WebSocket 注册逻辑。
- Docker、settings_prod、daemon_cli。

必须覆盖的场景：

- 空状态、加载状态、错误状态。
- 表单校验、删除确认、API 错误提示。
- 长列表或分页退化。
- 移动端 375px 宽度下表单、弹窗、侧边栏不遮挡。
- 所有页面继续复用 `base.html` / `navbar.html` / `sidebar.html`。

### A3 Infra/DB/Prod

负责范围：

- P0.3 Docker 镜像构建和验证。
- P0.4 SQLite 到 PostgreSQL 验证。
- P0.5 生产配置完善。

建议写入范围：

- `bodiagent/Dockerfile`
- `bodiagent/Dockerfile.daemon`
- `bodiagent/docker-compose.yml`
- `bodiagent/bodiagent/settings.py`
- `bodiagent/bodiagent/settings_prod.py`
- `bodiagent/.env.example`
- 部署、nginx、生产配置相关文档

避免修改：

- 业务模板页面和 daemon_cli 核心执行逻辑，除非为环境变量或健康检查提供接口。

必须覆盖的场景：

- `docker compose up` 后 `/health/` 返回 200。
- PostgreSQL 环境下 `migrate` 成功。
- PostgreSQL 环境下 pytest 全量通过，或记录明确阻塞项。
- `collectstatic` 可用。
- 容器非 root 或有明确说明。
- 环境变量缺失时错误信息可诊断。
- Redis、SMTP、Sentry 能通过配置接入；无凭据时提供 mock 或文档化验收步骤。

### A4 Daemon E2E

负责范围：

- P0.2 daemon_cli 端到端验证。
- 真实 AI CLI 执行链路。
- 可重复运行的 fake provider / test harness。
- 并发、取消、断线恢复、异常日志追踪。

建议写入范围：

- `bodiagent/daemon_cli/`
- `bodiagent/integration/tests/`
- daemon E2E 脚本和相关文档

避免修改：

- Web 前端模板。
- Docker compose 的主体结构，除非与 A3 对齐。

必须覆盖的场景：

- 至少一个真实 AI CLI 从接任务到回传结果完整走通；若凭据不可用，记录为人工验收阻塞。
- fake provider E2E 可在 CI 或本地稳定重复。
- 多任务并发受 Semaphore 控制。
- Cancel 能终止子进程并上报状态。
- 网络断开或心跳丢失时 executor 有预期行为。
- 任务日志可追溯。

### A5 Integration/QA

负责范围：

- P0 验收清单维护。
- 合并顺序和冲突协调。
- 全量测试、smoke test、移动端检查。
- 文档和路线图状态同步。
- 判断外部凭据、真实服务导致的阻塞项。

建议写入范围：

- `bodiagent/docs/`
- 验收脚本、测试报告、少量跨模块修正

避免修改：

- 大规模业务实现。A5 只做集成修复，不接管某个业务模块的大块开发。

必须覆盖的场景：

- 每个 P0 验收标准有明确状态：通过、失败、阻塞、待人工验收。
- 每次合并后运行相应测试。
- 汇总前端移动端问题和跨页面一致性问题。
- 对 Docker/PG/daemon/Chat 的联动链路做最终 smoke。

## 推荐启动顺序

第一批并行启动：

1. A1：先完成 WebSocket 路由和 smoke test，再进入 Chat UI。
2. A3：先完成 Docker compose 和 PostgreSQL migrate，这是其他任务的环境基线。
3. A2：先做非 Chat 的 CRUD 页面骨架和 API 闭环。
4. A4：先做 fake provider / E2E harness，再等 A3 环境稳定后跑真实链路。
5. A5：从第一天开始维护验收矩阵，不等开发完成。

关键依赖：

- A1 的 Chat UI 依赖 A1 自己的 WebSocket 路由注册。
- A2 的 CRUD PG 验证依赖 A3 的 PostgreSQL 环境。
- A4 的真实 daemon E2E 依赖 A3 的 Docker/Redis/PG 环境。
- P0.5 中 SMTP/Sentry 等真实服务依赖外部凭据，不能作为本地自动化完成的硬阻塞。

## 合并和冲突规则

- 共享文件变更必须保持小步提交思路，优先让 A5 集成。
- `base.html`、`navbar.html`、`sidebar.html` 属于高冲突文件，A1/A2 修改前需在任务说明中声明意图。
- `settings.py`、`settings_prod.py`、`docker-compose.yml` 默认由 A3 主责；其他 AGENT 需要配置项时先提交最小需求。
- `asgi.py` 默认由 A1 主责；A3 只在部署适配时协同。
- daemon_cli 默认由 A4 主责；A3 不直接修改执行器逻辑。

## 验收矩阵

| 项目 | 主责 | 状态 | 自动化要求 | 人工验收要求 |
|------|------|------|------------|--------------|
| P0.0 WebSocket 路由与 smoke test | A1 | 待开始 | WebSocket 连接、广播、断开测试 | 浏览器或 CLI 客户端实测 |
| P0.1 Chat UI | A1 | 待开始 | 基础前端/集成测试 | 发送消息、查看回复、375px 宽度检查 |
| P0.1 CRUD 页面 | A2 | 待开始 | 表单/API 闭环测试 | 创建/编辑/删除 Agent、Project、Autopilot、Token |
| P0.2 daemon E2E | A4 | 待开始 | fake provider 稳定回归 | 至少一个真实 AI CLI 完整链路 |
| P0.3 Docker | A3 | 待开始 | build、compose、healthcheck | 镜像大小、非 root、静态文件 |
| P0.4 PostgreSQL | A3 | 待开始 | migrate + pytest | fixtures 导入导出检查 |
| P0.5 生产配置 | A3 | 待开始 | settings_prod 启动、Redis/health 可测 | SMTP、Sentry、真实密钥注入 |
| P0 集成回归 | A5 | 待开始 | 全量 pytest、contract validation | 端到端 smoke 和文档状态确认 |

## 完成定义

本轮 P0 执行完成必须满足：

- 所有 P0 项目状态为“通过”或“有明确外部阻塞且已有替代验证”。
- 本地自动化测试和关键 smoke test 可重复运行。
- Docker + PostgreSQL 环境成为后续开发默认验证环境。
- 前端核心 CRUD 和 Chat 形成浏览器可用闭环。
- daemon_cli 至少有 fake provider 稳定 E2E；真实 AI CLI 链路在凭据可用时完成或列入人工阻塞。
- `bodiagent/docs/后续开发路线图.md` 或相关执行报告已同步实际完成状态。
