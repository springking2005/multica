# Daemon CLI Verification - Issues Found

## Issue 1: Broken absolute imports across daemon_cli/ package

**Test**: Task 1 - Daemon CLI importability
```bash
python3 -c "
from daemon_cli.providers.base import Provider, Event
from daemon_cli import config
from daemon_cli import identity
from daemon_cli import git_ops
from daemon_cli import cleanup as gc
print('All daemon imports OK')
"
```

**Expected**: All imports succeed, prints "All daemon imports OK"

**Actual**:
```
ModuleNotFoundError: No module named 'providers'
```
Then after fixing providers/__init__.py:
```
ModuleNotFoundError: No module named 'identity'
```
from `config.py:17: from identity import get_machine_id`

**Root Cause**: The daemon_cli package has a systematic import pattern problem. Files throughout the package use bare absolute imports (e.g., `from client import X`, `from config import X`) that only work when run from within the `daemon_cli/` directory with `.` on sys.path. When imported as a proper Python package via `from daemon_cli import X`, these imports fail because there are no top-level modules named `client`, `config`, etc.

This is the classic Python "dual-purpose module" problem: the same files are used both as a package (imported via `from daemon_cli.xxx import ...`) and as standalone modules (run via `python3 -m cli` from within the directory).

**Files affected** (all imports that were broken):

| File | Line | Broken import | Fix pattern |
|------|------|--------------|-------------|
| `providers/__init__.py` | 5-8 | `from providers.base/claude/openclaw/codex import ...` | try/except: `.base` / `base` |
| `providers/claude.py` | 10 | `from providers.base import ...` | try/except: `.base` / `base` |
| `providers/codex.py` | 10 | `from providers.base import ...` | try/except: `.base` / `base` |
| `providers/openclaw.py` | 10 | `from providers.base import ...` | try/except: `.base` / `base` |
| `config.py` | 17 | `from identity import ...` | try/except: `.identity` / `identity` |
| `executor.py` | 19-24 | `from client/config/cleanup/git_ops/providers/providers.base import ...` | try/except: `.xxx` / `xxx` |
| `cli.py` | 19-22 | `from client/config/executor/cleanup import ...` | try/except: `.xxx` / `xxx` |
| `tests/test_identity.py` | 8 | `from identity import ...` | `from daemon_cli.identity import ...` |
| `tests/test_config.py` | 8 | `from config import ...` | `from daemon_cli.config import ...` |
| `tests/test_cleanup.py` | 7 | `from cleanup import ...` | `from daemon_cli.cleanup import ...` |
| `tests/test_providers.py` | 5-9 | `from providers/providers.base/... import ...` | `from daemon_cli.providers/... import ...` |

**Severity**: Blocker - prevents all imports, CLI execution, and tests

**Fix applied**: 
- Source files (`cli.py`, `config.py`, `executor.py`, providers/*.py): Added `try/except ImportError` pattern for dual import support (relative imports for package context, absolute imports for script context)
- Test files (`tests/*.py`): Changed to package-qualified imports (`from daemon_cli.xxx import ...`) since tests always run from the project root

## Issue 2: Pre-existing Django test failure (api_test.py)

**Test**: Task 4 - Full test suite (`python3 -m pytest -q -p no:xdist -o "addopts="`)

**Expected**: All tests pass

**Actual**: `api_test.py` fails with:
```
RuntimeError: Database access not allowed, use the "django_db" mark, or the "db" or "transactional_db" fixtures to enable it.
```

**Root Cause**: `api_test.py` at the project root is a Django test that accesses the database at module level (line 35: `c.post("/api/auth/register", ...)`) during test collection, without the `django_db` marker. The conftest.py auto-enables DB access via the `db` fixture, but module-level code during collection does not have fixture support.

**Severity**: Non-blocking for daemon verification. This is a pre-existing issue in the Django project, unrelated to the daemon_cli package. The daemon_cli tests (26 tests) all pass.

**Fix**: Out of scope for daemon CLI verification. Would require either:
- Adding `@pytest.mark.django_db` to the api_test module, or
- Moving the module-level API calls into test functions with proper fixture setup
