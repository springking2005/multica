# 波笛智能体 API 功能验证报告

**日期**: 2026-05-11  
**测试环境**: Django development (SQLite, settings_dev.py)  
**测试工具**: Django Test Client (内存模式)

---

## 测试结果总览

| 指标 | 数值 |
|------|------|
| 总测试数 | 33 |
| 通过 | **33** |
| 失败 | **0** |
| 通过率 | **100%** |

---

## 修复概览

验证过程中发现并修复了 5 个代码缺陷：

| # | 问题 | 严重程度 | 修复文件 |
|---|------|---------|---------|
| 1 | CursorPagination 排序字段 `-created` 与模型 `created_at` 不匹配 | P0 | `bodiagent/pagination.py` (新), `bodiagent/settings.py` |
| 2 | Issue/Comment 创建时缺少 creator/author 自动填充 | P1 | `issues/serializers.py`, `issues/views.py` |
| 3 | AgentCreateSerializer 未包含 `skill_ids`/`daemon` 字段 | P1 | `agents/serializers.py` |
| 4 | TaskViewSet `dispatch` action 名与 DRF 框架方法冲突 | P0 | `agents/views.py` |
| 5 | TaskViewSet 缺少 `retrieve` 方法 | P1 | `agents/views.py` |

---

## 各模块测试详情

### Auth 模块 (6/6 通过)

| # | 测试 | URL | Method | Status | 结果 |
|---|------|-----|--------|--------|------|
| 1 | Health Check | `/health/` | GET | 200 | PASS |
| 2 | Register | `/api/auth/register` | POST | 201 | PASS |
| 3 | Login | `/api/auth/login` | POST | 200 | PASS |
| 4 | Verify Code | `/api/auth/verify-code` | POST | 200 | PASS |
| 5 | Token Refresh | `/api/auth/token-refresh` | POST | 200 | PASS |
| 6 | Get Me | `/api/me` | GET | 200 | PASS |

### Workspace 模块 (2/2 通过)

| # | 测试 | URL | Method | Status | 结果 |
|---|------|-----|--------|--------|------|
| 7 | Create Workspace | `/api/workspaces/` | POST | 201 | PASS |
| 8 | List Workspaces | `/api/workspaces/` | GET | 200 | PASS |

### Issues 模块 (9/9 通过)

| # | 测试 | URL | Method | Status | 结果 |
|---|------|-----|--------|--------|------|
| 9 | List Issues | `/api/issues` | GET | 200 | PASS |
| 10 | Create Issue | `/api/issues` | POST | 201 | PASS |
| 11 | Get Issue | `/api/issues/{id}` | GET | 200 | PASS |
| 12 | Update Issue | `/api/issues/{id}` | PATCH | 200 | PASS |
| 13 | Add Comment | `/api/issues/{id}/comments` | POST | 201 | PASS |
| 14 | List Comments | `/api/issues/{id}/comments` | GET | 200 | PASS |
| 15 | Search Issues | `/api/issues?search=...` | GET | 200 | PASS |
| 31 | Delete Issue | `/api/issues/{id}` | DELETE | 200 | PASS |

### Agents 模块 (8/8 通过)

| # | 测试 | URL | Method | Status | 结果 |
|---|------|-----|--------|--------|------|
| 16 | List Agents | `/api/agents` | GET | 200 | PASS |
| 17 | Daemon Register | `/api/daemon/register` | POST | 201 | PASS |
| 18 | Create Agent | `/api/agents` | POST | 201 | PASS |
| 19 | List Agents (non-empty) | `/api/agents` | GET | 200 | PASS |
| 20 | Get Agent Tasks | `/api/agents/{id}/tasks` | GET | 200 | PASS |
| 21 | Queue Task | `/api/tasks/queue` | POST | 201 | PASS |
| 22 | Task Status | `/api/daemon/tasks/{id}/status` | GET | 200 | PASS |
| 23 | Cancel Task | `/api/tasks/{id}/cancel` | POST | 200 | PASS |
| 32 | Delete Agent | `/api/agents/{id}` | DELETE | 200 | PASS |

### Inbox 模块 (3/3 通过)

| # | 测试 | URL | Method | Status | 结果 |
|---|------|-----|--------|--------|------|
| 24 | List Inbox | `/api/inbox` | GET | 200 | PASS |
| 25 | List Activities | `/api/activities` | GET | 200 | PASS |
| 26 | List Pins | `/api/pins` | GET | 200 | PASS |

### Projects 模块 (3/3 通过)

| # | 测试 | URL | Method | Status | 结果 |
|---|------|-----|--------|--------|------|
| 27 | List Projects | `/api/projects` | GET | 200 | PASS |
| 28 | Create Project | `/api/projects` | POST | 201 | PASS |
| 33 | Delete Project | `/api/projects/{id}` | DELETE | 200 | PASS |

### 其他 (2/2 通过)

| # | 测试 | URL | Method | Status | 结果 |
|---|------|-----|--------|--------|------|
| 29 | CLI Token | `/api/tokens/cli-token/` | POST | 200 | PASS |
| 30 | Logout | `/api/auth/logout` | POST | 200 | PASS |

---

## API 设计约定

以下为在测试过程中发现的非标准设计约定（非 bug）：

1. **Token 字段名**: 登录响应中 access token 使用 `token` 字段而非 simplejwt 标准的 `access`
2. **任务管理**: 任务无独立 `/api/tasks` 列表端点，通过 `/api/agents/{id}/tasks` 管理
3. **多租户**: 工作区作用域端点需要 `X-Workspace-ID` 请求头
4. **Delete 响应**: 删除操作返回 `{"ok": true}` 状态码 200（非 204）
5. **验证码 URL**: `/api/auth/verify-code` 非 `/api/auth/verify`
6. **字段命名**: Project 使用 `title` 非 `name`

---

## 修复文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `bodiagent/pagination.py` | 新建 | 自定义 CursorPagination，ordering = "-created_at" |
| `bodiagent/settings.py` | 修改 | DEFAULT_PAGINATION_CLASS 指向自定义分页类 |
| `issues/serializers.py` | 修改 | IssueCreateSerializer/CommentSerializer read_only_fields 添加 creator/author 字段 |
| `issues/views.py` | 修改 | IssueViewSet/CommentViewSet perform_create 自动设置 creator/author |
| `agents/serializers.py` | 修改 | AgentCreateSerializer.Meta.fields 添加 daemon, skill_ids |
| `agents/views.py` | 修改 | TaskViewSet dispatch 重命名为 dispatch_task；添加 RetrieveModelMixin |
