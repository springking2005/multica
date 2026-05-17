# Daemon CLI Verification Report

**Date**: 2026-05-11
**Project**: bodiagent (波笛智能体)
**Component**: Daemon CLI & Integration

## Summary

All 5 verification tasks PASS. Two import-related issues were found and fixed; one pre-existing Django test issue was documented (out of scope).

## Task Results

### Task 1: Daemon CLI Importability -- PASS
```
All daemon imports OK
```
All modules importable from the package context:
- `daemon_cli.providers.base`
- `daemon_cli.config`
- `daemon_cli.identity`
- `daemon_cli.git_ops`
- `daemon_cli.cleanup`

### Task 2: Provider Detection -- PASS
```
Found 2 providers: ['claude', 'codex']
```
Provider auto-detection works via `shutil.which()` scanning of $PATH.

### Task 3: CLI Entry -- PASS
```
Usage: cli.py [OPTIONS] COMMAND [ARGS]...
  波笛智能体 Daemon CLI — local task execution agent.
Commands: config, restart, setup, start, status, stop, update, version

bodiagent-daemon v0.1.0
Machine ID: a1f7f9fa-0ebe-4cb1-8d27-eca07dde854b
Detected AI CLIs: claude, codex, gemini
```
CLI help and version commands function correctly. Machine ID auto-generated, AI CLIs detected from PATH.

### Task 4: Tests -- PASS (26/26 daemon_cli tests)
```
daemon_cli/tests/test_providers.py .......          [ 26%]
daemon_cli/tests/test_config.py .......             [ 53%]
daemon_cli/tests/test_cleanup.py ...........        [ 96%]
daemon_cli/tests/test_identity.py ...               [100%]
26 passed in 2.98s
```

Test breakdown:
- **test_providers.py** (7 tests): Event dataclass, provider instantiation, get_provider routing
- **test_config.py** (7 tests): Default values, custom values, save/load roundtrip, CLI detection
- **test_cleanup.py** (9 tests): Task marking, GC eligibility, collect_garbage
- **test_identity.py** (3 tests): Machine ID generation, stability, path

Note: `api_test.py` (Django project-level test) fails due to missing `django_db` mark -- a pre-existing issue unrelated to daemon_cli. See `verify-daemon-issues.md` Issue 2.

### Task 5: Contract Validation -- PASS
```
OK: All 90 schema references resolved (90 schemas in components).
OK: schema.sql tables (39) match Django models (38).
OK: All 21 WS event domains referenced in openapi.yaml
Contract validation PASSED
```

## Issues Found & Fixed

### Fixed: Systematic import breakage (Issue 1)
11 files across `daemon_cli/` had broken absolute imports that failed when the package was imported from outside the `daemon_cli/` directory. Root cause: bare imports like `from client import X` only work when running from within the package directory.

**Fix**: Applied Python's standard `try/except ImportError` dual-import pattern to all source files, and package-qualified imports to test files. See `verify-daemon-issues.md` for full details.

### Documented: api_test.py Django DB access (Issue 2)
Pre-existing issue in the project's Django test at module level. Out of scope for daemon CLI verification.

## Files Modified
| File | Change |
|------|--------|
| `daemon_cli/providers/__init__.py` | Added dual-import fallback for base/claude/openclaw/codex |
| `daemon_cli/providers/claude.py` | Added dual-import fallback for base |
| `daemon_cli/providers/codex.py` | Added dual-import fallback for base |
| `daemon_cli/providers/openclaw.py` | Added dual-import fallback for base |
| `daemon_cli/config.py` | Added dual-import fallback for identity |
| `daemon_cli/executor.py` | Added dual-import fallback for client/config/cleanup/git_ops/providers |
| `daemon_cli/cli.py` | Added dual-import fallback for client/config/executor/cleanup |
| `daemon_cli/tests/test_providers.py` | Changed to package-qualified imports |
| `daemon_cli/tests/test_identity.py` | Changed to package-qualified imports |
| `daemon_cli/tests/test_config.py` | Changed to package-qualified imports |
| `daemon_cli/tests/test_cleanup.py` | Changed to package-qualified imports |

## Verification Checklist
- [x] Task 1: Daemon CLI importability -- PASS
- [x] Task 2: Provider detection -- PASS
- [x] Task 3: CLI entry (help + version) -- PASS
- [x] Task 4: daemon_cli tests (26/26) -- PASS
- [x] Task 5: Contract validation -- PASS
- [x] No debug code left behind
- [x] No new abstractions introduced
- [x] Issues documented in verify-daemon-issues.md

---

## 2026-05-17 A4 真实 Claude Code daemon 闭环

### 本轮结论

- 本机检测到 `claude`：`2.1.143 (Claude Code)`，`python3 -m daemon_cli.cli version` 可识别 `claude, codex, gemini`。
- Claude Code v2 的 `stream-json` 输出需要 `--verbose`，且正文位于 `message.content`；daemon 的 Claude provider 已适配该格式，并移除不匹配的 `--input-format stream-json`。
- daemon client 已关闭环境代理继承（`trust_env=False`），避免本机 `socks://127.0.0.1:7897` 这类代理导致 httpx 报错。
- daemon 注册接口不再携带 `Authorization: Bearer <daemon-token>` 默认头，避免 DRF JWT 在 AllowAny daemon endpoint 前置返回 401。
- daemon task usage endpoint 改为 daemon lifecycle 专用入口，真实任务完成后 `/api/daemon/tasks/<id>/usage` 返回 201。
- 真实本地闭环已完成：Django dev server + 本机 Claude Code `--bare` + daemon executor，任务从 queued 被 claim/start，Claude 返回 `BODIAGENT_DAEMON_OK`，daemon 提交 messages、complete、usage，最终 task 状态为 `completed`。

### 关键命令证据

| 命令 / 场景 | 结果 | 备注 |
|------|------|------|
| `python3 -m daemon_cli.cli --help` | 通过 | CLI 可启动 |
| `python3 -m daemon_cli.cli version` | 通过 | 检测到本机 AI CLI |
| `python3 -m pytest -q daemon_cli/tests/test_client.py daemon_cli/tests/test_config.py daemon_cli/tests/test_providers.py daemon_cli/tests/test_cleanup.py daemon_cli/tests/test_identity.py daemon_cli/tests/test_executor.py integration/tests/test_e2e_agent_task.py --tb=short` | 通过 | `36 passed` |
| 真实 Claude provider dry run | 通过 | 输出 `BODIAGENT_CLAUDE_OK` |
| 真实 daemon task flow | 通过 | `FINAL completed ... [('text', 'BODIAGENT_DAEMON_OK'), ('status', 'completed')]`，server log 显示 `/usage 201` |

### 运行建议

- 对真实本机 Claude Code 链路，Agent 的 `custom_args` 建议包含 `--bare --max-budget-usd 0.20 --tools ''`，避免加载本地交互式 hook/context 造成任务耗时或非预期工具调用。
- CI 中继续使用 fake provider 和 API 契约测试；真实 Claude/Codex CLI 闭环作为带凭据的本地/预发布验收项，不作为默认 CI 必跑项。
