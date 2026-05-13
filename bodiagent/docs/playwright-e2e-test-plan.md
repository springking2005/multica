# Playwright E2E Browser Test Plan for BodiAgent

**Date**: 2026-05-13
**Project**: BodiAgent, the Python/Django rewrite of Multica
**Frontend**: Django Templates + HTMX + small page-local JavaScript
**Backend**: Django 5.1, DRF, Channels, Celery, SQLite dev / PostgreSQL prod
**Test Account**: `admin@bodiagentteam.com` / `admin123`
**Dev Verification Code**: `888888`

## Context

BodiAgent already has a strong non-browser test baseline: roughly 270-290 tests cover models, API contracts, WebSocket consumers, login templates, daemon client behavior, and API-level E2E flows. These tests prove the server-side pieces and many contracts, but they do not execute browser JavaScript.

That gap matters because the web frontend is Django Templates + HTMX. Login/register redirects, form submission, dynamic list rendering, HTMX swaps, JSON-to-HTML rendering scripts, localStorage token persistence, WebSocket chat behavior, and mobile layout only work if browser JavaScript runs correctly. Django `Client` tests can verify HTML strings and API responses, but they cannot prove that a user can click through the app.

Playwright is already declared in `bodiagent/pyproject.toml` under the dev extras (`playwright>=1.49`) but is not yet used. This plan adds browser-based tests to cover the missing UI execution layer without duplicating all existing API/model tests.

## Evidence From Current Docs

| Source | Relevant Finding |
| --- | --- |
| `DESIGN.md` | BodiAgent UI completion source of truth: keep Django Templates + HTMX, but follow original Multica's compact headers, dense list/table surfaces, modal create/edit flows, sidebars, and explicit interaction states. |
| `docs/bugfix-auth-redirect.md` | Login/register previously rendered raw JSON because HTMX was missing, Django session was not created, and the redirect handler used the wrong HTMX event property. This is exactly the kind of regression Playwright should catch. |
| `docs/P0-执行验收状态-A5.md` | Dev/SQLite full pytest passed (`270 passed` in that report), Chat WebSocket route tests exist, but Chat UI and CRUD pages still need browser validation. |
| `docs/后续开发路线图.md` | P0 still requires browser-usable Chat UI, Agent/Project/Autopilot/Token pages, Docker/PG validation, and daemon E2E. |
| `docs/路线图审核-W1.md` | Several templates are shells or partial implementations: Issue detail may swap raw JSON, board drag/drop is not implemented, settings preferences are partly static, Agent edit/delete UI is missing. |
| `docs/用户操作手册-审核意见.md` | User-facing docs identify missing or API-only UI areas: workspace management, member invites, labels, Agent editing/skills, projects, autopilots, personal tokens. |
| `docs/verify-report.md` / `docs/verify-api-issues.md` | API behavior is known and should drive Playwright setup: `X-Workspace-ID` is required for scoped APIs, Project creation uses `title`, delete returns `200 {"ok": true}`, login returns `token`. |

## What Playwright Must Prove

1. A real browser can load the Django template pages.
2. HTMX is present where templates use `hx-*` attributes.
3. Login/register create a Django session, store JWTs in localStorage, and redirect to `/dashboard/` instead of showing raw JSON.
4. HTMX requests are sent to the correct API endpoints and render usable HTML, not raw JSON, unless raw JSON is explicitly expected.
5. Page-local JavaScript correctly converts DRF JSON responses into DOM for Dashboard, Issues board, Agents, Inbox, and any other JSON-backed page.
6. WebSocket Chat works from the browser, not only from Channels tests.
7. Core CRUD flows are usable from the browser for every P0 UI page that claims browser support.
8. Mobile width 375px remains usable for Chat, forms, modals, sidebar, and long text.

## Existing Coverage vs Browser Gaps

| Area | Existing Coverage | Browser Gap |
| --- | --- | --- |
| Auth | API tests, template string checks, bugfix docs for HTMX redirect | Fill form, submit with HTMX, verify session cookie, localStorage tokens, redirect, and no raw JSON |
| Dashboard | Template route and API checks | Dashboard widgets/data load in a browser via HTMX/JS |
| Workspace | API CRUD and membership behavior | Browser route after first login, current workspace context, UI/API-only boundaries made visible |
| Issues board | API CRUD/search/comments and board template | Board columns load via browser, JSON becomes cards, create modal works, unsupported drag/drop does not mislead |
| Issue detail | API detail/comments/activity | Detail page must not show raw JSON; comments submit and render in DOM |
| Agents | Model/API tests and list/create template | Dense management table, create/edit dialog, archive/restore/delete, search/filter, JSON validation, mobile modal |
| Projects | API tests | Multica-style project list/table, create/edit dialog, delete confirmation, priority/status controls, future detail-route acceptance |
| Autopilots | API/service tests | Template-driven empty state, create/edit schedule dialog, manual trigger, pause/enable, run status visibility |
| Inbox | Model/API tests and template | Mark read/archive actions mutate DOM and counters correctly |
| Chat | WebSocket consumer tests and API tests | Browser can create/open a chat, connect WS, send message, receive/broadcast, handle XSS text safely |
| Settings/Tokens | Profile template, token API | Profile save works; preferences persistence gap is visible; CLI token page generates token through browser |
| Daemon | daemon_cli unit/integration/fake provider tests | Optional browser-observed full chain: agent task starts, progress appears, inbox/result visible |
| Docker/PG | Docs require validation | Browser tests must run against dev SQLite first, then a smaller smoke pack against PostgreSQL/Docker |

## Proposed Test Layout

Use a BodiAgent-local Playwright suite so it does not conflict with the root Multica/Next.js Playwright setup.

```text
bodiagent/e2e/
├── playwright.config.ts
├── fixtures/
│   ├── django-server.fixture.ts
│   ├── auth.fixture.ts
│   ├── api.fixture.ts
│   └── factories.ts
├── helpers/
│   ├── selectors.ts
│   ├── htmx.ts
│   ├── csrf.ts
│   └── websocket.ts
└── specs/
    ├── auth-flow.spec.ts
    ├── dashboard.spec.ts
    ├── issues-board.spec.ts
    ├── issue-detail.spec.ts
    ├── agents-ui.spec.ts
    ├── projects-ui.spec.ts
    ├── autopilots-ui.spec.ts
    ├── inbox-ui.spec.ts
    ├── chat-ui.spec.ts
    ├── settings-and-tokens.spec.ts
    ├── responsive.spec.ts
    └── daemon-browser-observe.spec.ts
```

## Playwright Config

Recommended defaults:

- `baseURL`: `http://127.0.0.1:8000`
- Browser: Chromium first; Firefox/WebKit can be added after P0 is stable.
- Timeout: 30s per test, 10s action timeout.
- Screenshots: on failure.
- Trace: retain on failure.
- Video: retain on failure for normal specs, always retain for `@slow` daemon specs.
- Server startup: either auto-start with `python3 manage.py runserver 127.0.0.1:8000` or require an already-running server. Prefer explicit local script first to avoid port/database surprises.
- Database: SQLite dev for fast default browser tests; PostgreSQL smoke pack after Docker/PG path is available.

Suggested commands:

```bash
cd bodiagent
python3 manage.py migrate
python3 manage.py runserver 127.0.0.1:8000
python3 -m playwright install chromium
python3 -m playwright test e2e/specs --grep-invert @slow
```

If Playwright's Python runner is not available through the installed package in this environment, add a minimal documented runner dependency or use the official Python Playwright CLI installed by `pip install -e ".[dev]"`.

## Test Data and Login Strategy

Use browser interactions for the flow being tested. Use API-assisted setup only for prerequisites that are not the target of that test.

- Auth specs must use the real login/register forms.
- Non-auth specs may log in through a helper that posts to `/api/auth/login`, seeds session cookies/localStorage, and opens `/dashboard/`.
- Workspace-scoped API setup must include `X-Workspace-ID`.
- Data names must include a timestamp or UUID suffix.
- Tests should clean up created Issue, Agent, Project, Autopilot, Inbox, Chat, and Token rows through API or DB fixtures.
- Default dev code is `888888` for verification-code flows.

## HTMX-Specific Rules

1. Assert HTMX is loaded on every page that uses `hx-*`.
2. Prefer waiting on HTMX lifecycle or network response: `page.waitForResponse()`, `htmx:afterRequest`, selector changes, or URL changes.
3. Never use arbitrary sleep unless testing debounce/timing behavior explicitly.
4. For JSON-backed templates, assert the final DOM contains rendered cards/rows and does not show raw JSON braces as the primary content.
5. Verify error targets: failed form submissions should render into the intended error container, not replace the full page with JSON.

## P0 Browser Specs

### 1. `auth-flow.spec.ts` — Login/Register Regression Guard

| Test | Steps | Assertions |
| --- | --- | --- |
| Login page loads HTMX | `goto('/login/')` | Login form visible, `window.htmx` exists, form has correct `hx-post='/api/auth/login'` |
| Login succeeds via browser | Fill `admin@bodiagentteam.com` / `admin123`, submit | Redirects to `/dashboard/`, `sessionid` cookie exists, `bodiagent_token` and `bodiagent_refresh` localStorage keys exist |
| Login does not show raw JSON | Submit valid login | Body does not become `{"token":...}` JSON; URL changes to dashboard |
| Login failure renders inline error | Fill wrong password, submit | Still on `/login/`, error container visible, no token/session created |
| Register succeeds via browser | Fill unique name/email/password, submit | Redirects to `/dashboard/`, session cookie and tokens exist |
| Register failure stays on page | Submit duplicate email or invalid password | Inline error visible; no raw JSON page |
| Verify-code login path | Send/verify dev code `888888` if exposed in UI or via test helper | New/existing user authenticated and redirected correctly |
| Logout | Authenticated browser clicks logout | Session invalidated, local tokens cleared, protected routes redirect to `/login/` |

### 2. `dashboard.spec.ts` — Authenticated Landing Page

| Test | Steps | Assertions |
| --- | --- | --- |
| Dashboard requires session | Clear cookies, visit `/dashboard/` | Redirects to `/login/` |
| Dashboard renders after login | Login and visit `/dashboard/` | Greeting visible, no server error, primary navigation visible |
| Dashboard dynamic sections load | Wait for API-backed cards/widgets | Widgets render meaningful empty/data states, not raw JSON |
| Workspace context visible | Seed workspace membership, open dashboard | Current workspace is shown or available in page context |

### 3. `issues-board.spec.ts` — Board UI and Create Flow

| Test | Steps | Assertions |
| --- | --- | --- |
| Board requires auth | Visit `/issues/` unauthenticated | Redirects to login |
| Board columns load | Seed issues in visible statuses, open `/issues/` | Backlog/Todo/In Progress/In Review/Done columns visible; counts match seeded data |
| JSON renders as cards | Wait for `/api/issues` responses | Issue cards render title/number/priority; raw JSON is not displayed |
| Create issue from modal | Click New Issue, fill title/description/priority, submit | API returns 201, modal closes or success shown, new card appears |
| Create validation error | Submit missing title | Error shown in modal/target; no blank issue appears |
| Card opens detail | Click created issue card | Navigates to `/issues/<uuid>/`; detail shell loads |
| Unsupported quick-create is safe | Click column `+` if present | Either no-op with no error, or implemented quick-create opens; no console exception |
| Board mobile width | Set viewport 375px, open board | Header/actions/columns remain reachable, no modal clipping |

### 4. `issue-detail.spec.ts` — Detail, Comments, Activity

| Test | Steps | Assertions |
| --- | --- | --- |
| Detail loads seeded issue | Open `/issues/<id>/` | Title/description/properties visible after HTMX/JS settles |
| Detail does not raw-swap JSON | Wait for issue API | Main content is rendered HTML, not raw DRF JSON |
| Update status/priority | Change sidebar dropdowns | PATCH sent, saved state appears, UI updates, reload persists |
| Add comment | Fill comment, submit | Comment appears in DOM and API returns 201 |
| Empty comment rejected | Submit empty comment | Button disabled or validation error shown |
| Activity timeline loads | Seed activity or update issue | Activity row appears, not raw JSON |
| Assignment to member/agent | Seed member/agent, choose assignee from sidebar | Assignee display updates; inbox side effect can be checked via API/UI |

### 5. `agents-ui.spec.ts` — Agent Management UI

| Test | Steps | Assertions |
| --- | --- | --- |
| Agents page loads dense table | Open `/agents/` | Compact header with count and Create Agent button, toolbar, table/list rows, no card-grid-only desktop layout |
| Empty state is actionable | Use workspace with no agents | Empty state has one primary create action and daemon/token prerequisite link when no daemon is available |
| Create agent | Open dialog, fill name/provider/model/daemon/instructions/max concurrency, submit | API returns success, dialog closes or saved state appears, new row shows provider/model/status/runtime |
| Advanced JSON validation | Enter invalid custom env/args/MCP JSON in dialog | Submit is blocked or inline error appears; dialog stays open; page is not replaced by JSON |
| Search/filter/sort | Seed multiple agents, use search/status/sort controls | Matching rows update, count reflects visible set, cleared search restores rows |
| Edit agent | Open row action Edit, change description/model/instructions, save | Row updates and reload persists |
| Archive and restore | Use row action Archive, switch archived view, Restore | Row leaves active table, appears in archived view, then returns active |
| Delete agent | Use row action Delete and confirm | Row removed after API success; destructive copy names the agent |
| Cancel task action | For an agent with running task or mocked running state, click Cancel Task | Request is sent and row status/result updates, or action is disabled with an explicit reason |
| Mobile modal and rows | 375px viewport, open dialog and row actions | Fields/buttons usable without overflow; actions are not hover-only |

### 6. `projects-ui.spec.ts` — Project Management UI

Projects are API-backed and must be completed as a Multica-style browser workflow: compact list/table, modal creation/editing, inline properties, and clear future-detail behavior.

| Test | Steps | Assertions |
| --- | --- | --- |
| Projects route loads dense table | Open `/projects/` | Compact header with count and New Project button, toolbar, table/list rows or empty state |
| Create project | Open dialog, fill title/description/icon/priority/status/lead where writable | API 201 uses `title`, not `name`; new row appears with title and metadata |
| Create validation error | Submit missing title or invalid field | Inline error appears in dialog; no blank project row; no raw JSON page |
| Project list renders API data | Seed projects via API, reload | Rows show icon/title/description/priority/status/progress/lead/created date; no raw JSON |
| Search/filter/sort | Seed multiple projects, use toolbar controls | Visible rows and count update without full-page JSON replacement |
| Edit project | Open row action Edit, change description/priority/status/lead when writable | Row updates and reload persists; read-only fields are visibly disabled with reason |
| Delete project | Use row action Delete and confirm | Confirmation names project; row removed after success |
| Future detail link contract | Click a project row/title | Navigates to `/projects/<id>/` if implemented; otherwise title is not presented as a broken link |
| Mobile project rows | 375px viewport, use create/edit/delete flow | Stacked rows and dialog controls fit; primary action remains reachable |

### 7. `autopilots-ui.spec.ts` — Autopilot Management UI

| Test | Steps | Assertions |
| --- | --- | --- |
| Autopilots route loads | Open `/autopilots/` | Compact header with count/New Autopilot button; list rows or template empty state visible |
| Template empty state opens dialog | In empty workspace, click Daily Summary/PR Review/Bug Triage/etc. template | Create dialog opens with prefilled title/description/schedule/output mode |
| Create scheduled autopilot | Fill title, prompt/description, agent, output mode, frequency/time/timezone, submit | Autopilot row appears with agent, trigger summary, status, and next/last run data when available |
| Cron/custom schedule validation | Choose custom cron or invalid schedule | Preview updates for valid input; invalid input shows inline error and blocks submit |
| Edit autopilot | Open row action Edit, change schedule/output mode/agent | Row updates and reload persists |
| Manual trigger observe | Click Manual Run on row | Request succeeds; row shows running/result state or last run timestamp without requiring raw API inspection |
| Pause and enable | Toggle Pause/Enable | Status badge changes and persists after reload |
| Delete autopilot | Use row action Delete and confirm | Row removed after success |
| Mobile autopilot dialog | 375px viewport, create from template | Schedule fields, footer buttons, and errors remain reachable |

### 8. `inbox-ui.spec.ts` — Notifications

| Test | Steps | Assertions |
| --- | --- | --- |
| Inbox loads | Seed inbox items, open `/inbox/` | Items render with title, type, time, read indicator |
| Mark all read | Click Mark all read | Items/counter update without refresh |
| Archive read | Mark read then archive read | Archived items leave list |
| Open linked issue | Click inbox item with `issue_id` | Navigates to issue detail; item read state changes if designed |
| Empty state | No inbox items | Empty state visible |
| Mobile list | 375px viewport | Buttons and rows usable |

### 9. `chat-ui.spec.ts` — Browser WebSocket Chat

| Test | Steps | Assertions |
| --- | --- | --- |
| Chat route requires auth | Visit `/chat/` unauthenticated | Redirects to login |
| Chat page loads | Login, open `/chat/` | Chat shell visible; no console errors |
| Create/open session | Choose agent and create a session, or open an existing session from the rail | Session is selected; transcript and composer are visible |
| WebSocket connects | Open chat session | Browser establishes `ws/chat/<session_id>/` connection |
| Send message | Type text and submit | Message appears in local transcript and/or API messages list |
| Two-browser broadcast | Open same session in two contexts, send from one | Other context receives message |
| XSS text safety | Send `<script>alert(1)</script>` | Text renders escaped; no dialog executes |
| Disconnect/reconnect behavior | Close/reload or temporarily cut WS if feasible | UI does not crash; reconnect/error state visible |
| Mobile chat | 375px viewport | Input and transcript remain usable |

### 10. `settings-and-tokens.spec.ts` — Profile, Preferences, CLI Token

| Test | Steps | Assertions |
| --- | --- | --- |
| Settings loads | Open `/settings/` | Profile form, preferences, notification section visible |
| Update profile | Change name/avatar/email if safe | PATCH `/api/me/` succeeds; DOM shows saved state |
| Theme local setting | Toggle theme | localStorage changes and theme class/style changes if implemented |
| Language persistence gap | Change language | Either persisted through API or explicitly remains known non-persistent UI |
| Notification preferences | Toggle if wired | API update and reload persistence, or known non-persistent gap captured |
| Token page loads | Open `/settings/tokens/` | Token shell visible |
| Generate CLI token | Click generate | Token appears once; no raw JSON full-page replacement |
| Copy token | Generate token, click Copy | Clipboard receives token value where browser permissions allow; copied state appears |
| Revoke token | Click revoke on a token row and confirm | Row removed or marked revoked after success; reload persists |

### 11. `responsive.spec.ts` — 375px P0 Smoke

Run core pages at `375x812`:

- `/dashboard/`
- `/issues/`
- `/issues/<id>/`
- `/agents/`
- `/projects/`
- `/autopilots/`
- `/inbox/`
- `/chat/`
- `/settings/`

Assertions: primary navigation reachable, no horizontal page-level overflow except intended kanban column scrolling, modals fit, submit buttons reachable, long text does not cover controls.

## P1 Browser Specs

| Area | Scenarios |
| --- | --- |
| Workspace management | Create/edit/delete workspace UI once implemented; member invite/role/remove UI once implemented |
| Labels | Label create/list/apply/remove UI once implemented |
| Pins | Pin/unpin/reorder issue/project UI once implemented |
| Search/filter | Issue/project search results render and link correctly |
| Permissions | Owner/Admin/Member browser sessions see correct actions and cannot access unauthorized operations |
| PostgreSQL browser smoke | Run auth, issue create, agent create, inbox, chat smoke under Docker/PG |
| Error handling | API 400/401/403/500 responses render friendly errors in HTMX targets |

## P2 / Optional Slow Specs

### `daemon-browser-observe.spec.ts` (`@slow`)

Requires daemon binary, at least one AI CLI or fake provider, and a running server.

| Test | Steps | Assertions |
| --- | --- | --- |
| Daemon visible in UI/API | Start daemon/fake provider | Daemon/runtime appears where exposed |
| Agent bound to daemon | Create agent with daemon/provider | Agent card/detail shows provider and active state |
| Assign issue to agent | Create issue and assign to agent | Task queued; issue/activity/inbox shows execution started |
| Task reaches terminal state | Wait for fake/real provider completion | Issue timeline and inbox show completed/failed result |
| Cancel path | Start long-running fake task, cancel | UI/API show cancelled; no orphan running state |

Real Claude/Codex execution remains a manual or separately gated acceptance path until credentials and CLI environment are available.

## Infrastructure Tasks

1. Add `bodiagent/e2e/playwright.config.ts` or equivalent Python Playwright config/runner documentation.
2. Add browser install instructions to `docs/启动指南.md` after the core suite exists.
3. Add fixtures for authenticated browser state, API data setup, workspace header, and cleanup.
4. Add helper assertions for HTMX loaded, no raw JSON page, no console errors, and mobile overflow.
5. Add selectors/test IDs only where semantic roles and labels are insufficient; prefer accessible names first.
6. Add CI job only after the local suite is stable. First CI target should be `auth-flow`, `issues-board`, `agents-ui`, `projects-ui`, `autopilots-ui`, `inbox-ui`, and `settings-and-tokens` smoke tests.

## Verification Plan

Before merging the Playwright suite:

```bash
cd bodiagent
python3 manage.py check
python3 scripts/validate_contracts.py
python3 -m pytest -q
python3 -m playwright test e2e/specs --grep-invert @slow
```

After Docker/PG is ready:

```bash
cd bodiagent
docker compose up -d db redis web
curl -fsS http://127.0.0.1:8000/health/
python3 -m playwright test e2e/specs/auth-flow.spec.ts e2e/specs/issues-board.spec.ts e2e/specs/chat-ui.spec.ts
```

## Implementation Order

| Phase | Work | Exit Criteria |
| --- | --- | --- |
| 1 | Playwright harness and auth tests | Login/register no longer regress to raw JSON; session + redirect verified in browser |
| 2 | Dashboard, issues board, issue detail | HTMX/JSON rendering and comment/create flows verified |
| 3 | Shared UI completion from `DESIGN.md` | Page header, toolbar, table/list, dialog, alert, property-row, empty-state patterns are available to templates |
| 4 | Agents, projects, autopilots | Multica-style dense management flows have create/edit/delete/search/filter and no dead controls |
| 5 | Inbox, settings/tokens | Notification and token browser flows mutate DOM and persist correctly |
| 6 | Chat UI WebSocket | Browser WS connect/send/broadcast/XSS/mobile verified |
| 7 | Responsive and PG/Docker smoke | 375px smoke and PostgreSQL browser smoke are repeatable |
| 8 | Optional daemon observed flow | Fake provider browser-observed task lifecycle passes under `@slow` |

## Target Test Count

| Spec | Estimated Tests |
| --- | ---: |
| `auth-flow.spec.ts` | 8 |
| `dashboard.spec.ts` | 4 |
| `issues-board.spec.ts` | 8 |
| `issue-detail.spec.ts` | 7 |
| `agents-ui.spec.ts` | 10 |
| `projects-ui.spec.ts` | 9 |
| `autopilots-ui.spec.ts` | 9 |
| `inbox-ui.spec.ts` | 6 |
| `chat-ui.spec.ts` | 9 |
| `settings-and-tokens.spec.ts` | 9 |
| `responsive.spec.ts` | 9 route smokes |
| `daemon-browser-observe.spec.ts` | 5 optional slow |
| **Total** | **91 planned browser checks** |

This browser suite is intentionally narrower than the existing model/API/contract suite. Its job is to prove the real user path: load templates, execute HTMX and JavaScript, manipulate the DOM, maintain sessions/tokens, use WebSocket Chat, and complete the P0 UI flows in an actual browser.
