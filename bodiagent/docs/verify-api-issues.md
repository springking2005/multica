# API 验证问题清单

## 已修复的问题

### 问题 1: CursorPagination 默认排序字段 `-created` 与项目字段名 `created_at` 不兼容 [已修复]

- **严重程度**: 严重 (P0)
- **影响范围**: 所有使用默认分页的列表接口（Workspace、Issue、Agent 等）
- **URL**: `GET /api/workspaces/`, `GET /api/issues`, 等
- **实际响应**: 500 Internal Server Error
- **错误**: `FieldError: Cannot resolve keyword 'created' into field. Choices are: ..., created_at, ...`
- **根本原因**: DRF 的 `CursorPagination` 默认 `ordering = '-created'`，但项目所有模型使用 `created_at`
- **修复**: 
  - 文件: `bodiagent/pagination.py` (新建) — 创建 `CreatedAtCursorPagination(CursorPagination)` 覆盖 `ordering = "-created_at"`
  - 文件: `bodiagent/settings.py` — 将 `DEFAULT_PAGINATION_CLASS` 改为 `bodiagent.pagination.CreatedAtCursorPagination`

### 问题 2: Issue/Agent 等 CRUD 接口创建时需要 `creator_type`/`creator_id`/`author_type`/`author_id` [已修复]

- **严重程度**: 高 (P1)
- **影响范围**: Issue 创建、Comment 创建
- **URL**: `POST /api/issues`, `POST /api/issues/{id}/comments`
- **实际响应**: 400 — `creator_type`/`creator_id`/`author_type`/`author_id` 必填
- **根本原因**: 
  - `IssueCreateSerializer` 未将 `creator_type`/`creator_id` 标记为 read_only，且 `perform_create` 未自动设置
  - `CommentSerializer` 未将 `author_type`/`author_id` 标记为 read_only，且 `perform_create` 未自动设置
- **修复**:
  - 文件: `issues/serializers.py` — `IssueCreateSerializer.Meta.read_only_fields` 添加 `creator_type`/`creator_id`；`CommentSerializer.Meta.read_only_fields` 添加 `author_type`/`author_id`
  - 文件: `issues/views.py` — `IssueViewSet.perform_create()` 自动设置 `creator_type="user"`, `creator_id=request.user.id`；`CommentViewSet.perform_create()` 自动设置 `author_type="user"`, `author_id=request.user.id`

### 问题 3: AgentCreateSerializer `skill_ids` 和 `daemon` 字段未包含在 `Meta.fields` [已修复]

- **严重程度**: 高 (P1)
- **影响范围**: Agent 创建
- **URL**: `POST /api/agents`
- **实际响应**: 500 Internal Server Error
- **错误**: `AssertionError: The field 'skill_ids' was declared on serializer AgentCreateSerializer, but has not been included in the 'fields' option.`
- **根本原因**: `AgentCreateSerializer` 继承 `AgentSerializer.Meta` 使用 `pass`，未追加新声明的字段
- **修复**: `AgentCreateSerializer.Meta.fields` 改为 `AgentSerializer.Meta.fields + ["daemon", "skill_ids"]`

### 问题 4: TaskViewSet 自定义 action 名 `dispatch` 与 DRF 框架方法冲突 [已修复]

- **严重程度**: 严重 (P0)
- **影响范围**: 所有 TaskViewSet 端点
- **URL**: 所有 `/api/tasks/*` 和 `/api/daemon/tasks/*` 路径
- **实际响应**: 500 Internal Server Error
- **错误**: `AssertionError: Expected view TaskViewSet to be called with a URL keyword argument named "task_id"`
- **根本原因**: `@action(detail=True, methods=["post"])` 命名为 `dispatch`，覆盖了 DRF ViewSetMixin 的内置 `dispatch()` 方法
- **修复**: 重命名为 `dispatch_task`，添加显式 `url_path="dispatch"` 保持 URL 兼容

### 问题 5: TaskViewSet 缺少 `retrieve` 方法导致 daemon task status 端点 500 [已修复]

- **严重程度**: 高 (P1)
- **影响范围**: Daemon 任务状态查询
- **URL**: `GET /api/daemon/tasks/{task_id}/status`
- **实际响应**: 500 Internal Server Error
- **错误**: `AttributeError: 'TaskViewSet' object has no attribute 'retrieve'`
- **根本原因**: URL 配置将 `retrieve` 映射到 TaskViewSet，但 TaskViewSet 继承 `GenericViewSet` 未包含 `RetrieveModelMixin`
- **修复**: TaskViewSet 添加 `mixins.RetrieveModelMixin`

---

## API 设计约定 (非 Bug)

### 约定 1: 登录返回的 token 字段名为 `token` 非 `access`

- 响应格式: `{"token": "jwt...", "refresh": "jwt...", "user": {...}}`
- 相比 simplejwt 标准的 `access` 字段，本项目使用 `token` 作为命名
- 调用方需使用 `token` 字段获取 access token

### 约定 2: `/api/tasks` 无标准 CRUD 列表接口

- `GET /api/tasks` 返回 404 — 无 list 端点
- 任务列表通过 `GET /api/agents/{agent_id}/tasks` 获取
- 任务创建通过 `POST /api/tasks/queue` 实现
- 此为架构设计决策

### 约定 3: 工作区作用域端点需要 `X-Workspace-ID` 头

- Agent、Issue、Inbox、Project 等端点使用 `WorkspaceScopedMixin`
- 必须通过 `X-Workspace-ID` 请求头提供 workspace UUID

### 约定 4: Delete 操作返回 200 + `{"ok": true}` 而非 204

- Issue、Agent、Comment、Project 等的 destroy 重写为 `Response({"ok": True})`
- 默认状态码为 200（非标准的 204 No Content）

### 约定 5: Daemon 注册使用 `machine_id` (UUID) 字段

- `POST /api/daemon/register` 需要 `{"machine_id": "<UUID>", "device_name": "..."}`
- 非测试指令中的 `name`/`hostname`

### 约定 6: 验证码 URL 为 `/api/auth/verify-code` 非 `/api/auth/verify`

### 约定 7: Project 创建使用 `title` 字段非 `name`
