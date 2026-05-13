# Design

## Source of truth
- Status: Active draft
- Last refreshed: 2026-05-13
- Primary product surfaces: Django Templates + HTMX browser UI for BodiAgent, the Python rewrite of Multica.
- Evidence reviewed:
  - `docs/design.md` for original Multica visual system.
  - `packages/views/agents/components/agents-page.tsx`
  - `packages/views/projects/components/projects-page.tsx`
  - `packages/views/projects/components/project-detail.tsx`
  - `packages/views/autopilots/components/autopilots-page.tsx`
  - `packages/views/autopilots/components/autopilot-dialog.tsx`
  - `bodiagent/frontend/templates/agents/list.html`
  - `bodiagent/frontend/templates/projects/list.html`
  - `bodiagent/frontend/templates/autopilots/list.html`
  - `bodiagent/frontend/templates/chat/detail.html`
  - `bodiagent/frontend/templates/issues/detail.html`
  - `bodiagent/frontend/templates/settings/tokens.html`
  - `bodiagent/docs/用户操作手册-审核意见.md`
  - `bodiagent/docs/路线图审核-W1.md`
  - `bodiagent/docs/playwright-e2e-test-plan.md`

## Brand
- Personality: restrained, operational, precise, work-focused.
- Trust signals: dense information layout, predictable row actions, explicit save/error states, visible runtime/agent status.
- Avoid: marketing-style hero layouts, oversized cards, decorative gradients, color-heavy dashboards, unimplemented controls that imply capability.

## Product goals
- Goals:
  - Preserve the original Multica workflows while implementing them in Django Templates + HTMX.
  - Turn skeleton/API-only pages into complete browser workflows.
  - Make every P0 surface usable at 375px and desktop widths.
  - Keep API-backed pages from rendering raw JSON into the UI.
- Non-goals:
  - Recreating the React component system in Django.
  - Introducing a SPA framework.
  - Pixel-perfect parity with Multica React pages.
- Success signals:
  - Users can create, edit, search/filter, inspect, archive/delete, and recover from errors without leaving the browser.
  - Playwright validates JS/HTMX behavior rather than only server responses.

## Personas and jobs
- Primary personas:
  - Team owner/admin configuring agents, projects, autopilots, tokens, and daemon access.
  - Team member triaging issues, comments, inbox notifications, and project work.
  - AI-native developer monitoring agent and daemon execution.
- User jobs:
  - Create an issue, assign it to a human or agent, and follow execution.
  - Create and tune agents for different providers/runtimes.
  - Group issue work by project and inspect progress.
  - Schedule recurring work through Autopilot.
  - Chat with an agent over a live WebSocket session.
  - Generate CLI tokens and connect daemon CLI.
- Key contexts of use: desktop work sessions, local development setup, occasional mobile review at 375px width.

## Information architecture
- Primary navigation: Dashboard, Issues, Agents, Projects, Autopilots, Inbox, Chat, Settings.
- Core routes/screens:
  - `/issues/`: board/list issue management.
  - `/issues/<uuid>/`: issue detail with editable title/body, comments, timeline, and property sidebar.
  - `/agents/`: agent management table with filters, status, runtime, create/edit/archive/restore/delete.
  - `/projects/`: project table and create dialog.
  - `/projects/<uuid>/` when added: project detail with properties, progress, resources, and project-scoped issues.
  - `/autopilots/`: autopilot list, templates, schedule/output dialog, run/status visibility.
  - `/chat/` and `/chat/<uuid>/`: session selection, transcript, composer, WebSocket state.
  - `/settings/tokens/`: CLI token creation, one-time reveal, token list, revoke.
- Content hierarchy:
  - Page header: icon, title, count, one primary action.
  - Toolbar: search, scope/filter segments, sort, secondary links.
  - Main surface: dense rows/table first; cards only for empty-state templates or mobile fallbacks.
  - Modal/dialog: create/edit details.
  - Side panel: properties and metadata for detail pages.

## Design principles
- Principle 1: Lists are the default work surface. Prefer compact rows over large cards for Agents, Projects, and Autopilots.
- Principle 2: Creation is modal, editing is contextual. Use dialogs for creation and inline row/sidebar controls for status, priority, assignee, and schedule.
- Principle 3: Empty states should offer the first useful action, not marketing copy.
- Principle 4: Skeleton pages must either be fully functional or clearly absent; never ship dead buttons.
- Tradeoffs:
  - BodiAgent may use Tailwind gray/blue utilities until tokenization is ported, but layout and interaction should follow Multica's restrained system.
  - HTMX and small JavaScript modules are acceptable; do not introduce React/Vue just to mirror original components.

## Visual language
- Color:
  - Base UI is neutral: white/gray surfaces, subtle borders, muted text.
  - Blue is allowed only as current BodiAgent primary action until semantic tokens are ported.
  - Status colors stay small: dots, badges, icons, progress bars.
- Typography:
  - Use `text-sm` as the default UI size.
  - Page title rows should be compact, closer to Multica `text-sm font-medium` than oversized dashboard headings.
  - Avoid `font-bold` on dense app surfaces; use `font-medium`.
- Spacing/layout rhythm:
  - Page header height around 44-48px.
  - Dense row height around 44px on desktop.
  - Toolbars use 8-12px gaps.
  - Dialog forms use grouped sections, not one long page form.
- Shape/radius/elevation:
  - Radius no larger than 8px for cards/dialogs.
  - Prefer borders and subtle background over shadows.
  - No nested cards.
- Motion:
  - Use simple color transitions.
  - No scale or decorative animation.
- Imagery/iconography:
  - Use small functional icons matching original Multica concepts: Bot, Folder, Zap, Inbox, Search, Plus, Play/Pause.
  - In Django templates use inline SVG only where no icon library is available.

## Components
- Existing components to reuse conceptually from Multica:
  - `PageHeader`: compact route header with icon/title/count/action.
  - `DataTable` rows: dense hover rows with pinned row actions.
  - `CreateAgentDialog`: modal create/edit with runtime/provider/model/instructions and advanced JSON.
  - `ProjectRow`: icon/title, priority dropdown, status dropdown, progress, lead picker, created date.
  - `AutopilotDialog`: title/description editor, agent picker, output mode, trigger schedule, timezone.
  - `ProjectDetail`: editable title/description, properties sidebar, progress, resources, project-scoped issues.
  - `IssueDetail`: editable content, comments, timeline, property sidebar.
- New/changed BodiAgent template components:
  - `ba-page-header`: compact header used by all skeleton pages.
  - `ba-toolbar`: search/filter/sort row.
  - `ba-table`: semantic table/list row pattern for dense management pages.
  - `ba-dialog`: Alpine-backed modal with explicit title, body, footer, close, Escape, focus return.
  - `ba-property-row`: label/value row for sidebars.
  - `ba-empty-state`: icon, one sentence, one primary action.
  - `ba-alert`: inline success/error region.
- Variants and states:
  - Loading: skeleton rows, not only "加载中".
  - Empty: contextual CTA.
  - Error: retry button and API error summary.
  - Disabled: visible reason for unavailable submit/actions.
  - Archived/paused/offline: small badge/dot.
- Token/component ownership:
  - Until token porting, keep styles local to templates/static CSS and use a shared class naming convention in `frontend/static/css/app.css`.

## P0 UI Completion Design

### Agents
- Original Multica flow: header -> search/scope/sort/availability toolbar -> dense table -> create dialog -> row actions -> archived view.
- BodiAgent design:
  - Replace the 3-column card grid as the default desktop view with a dense row table.
  - Header: Bot icon, "智能体", active count, "创建智能体".
  - Toolbar:
    - Search by name/description/provider.
    - Segment: 我的 / 全部.
    - Chips: 全部 / 在线 / 不稳定 / 离线 when runtime presence is available; otherwise show status chips: 活跃 / 已归档.
    - Sort: 最近活动 / 名称 / 创建时间.
    - Link: 查看已归档.
  - Row columns:
    - Agent name + provider/model.
    - Runtime/daemon.
    - Status/visibility.
    - Max concurrency.
    - Owner if in "全部".
    - Created/updated.
    - Action menu: 编辑, 复制配置, 归档/恢复, 取消任务, 删除.
  - Create/edit dialog:
    - Basic: name, description, daemon, provider, model, visibility.
    - Instructions textarea.
    - Advanced accordion: max concurrency, custom env JSON, custom args JSON, MCP config JSON.
    - Validate JSON before submit and keep dialog open on error.
  - Empty state: "还没有智能体" plus "创建智能体"; if no daemon exists, show secondary link to token/daemon setup.

### Projects
- Original Multica flow: compact project rows with inline property controls and a separate detail page.
- BodiAgent design:
  - `/projects/` becomes a table/list, not a permanent creation form.
  - Header: Folder icon, "项目", count, "新建项目".
  - Table columns:
    - Icon + title + short description.
    - Priority dropdown.
    - Status dropdown.
    - Progress placeholder from issue counts if API returns it; otherwise show `--`.
    - Lead picker using members/agents when API supports it.
    - Created date.
    - Actions: 编辑, 删除.
  - Create/edit dialog:
    - Title, description, icon, priority, status, lead.
    - Status should be editable only in update flow if create serializer keeps it read-only.
  - Future `/projects/<id>/` detail:
    - Left/main: project-scoped issue board/list with "New Issue" pre-bound to project.
    - Right/sidebar: project icon/title, status, priority, lead, progress, resources, pin/delete.
    - Resources section mirrors Multica `ProjectResourcesSection`; until repo/resource API is complete, render an explicit "资源管理待接入" disabled state.

### Autopilots
- Original Multica flow: list rows plus template-driven empty state and a rich create/edit dialog.
- BodiAgent design:
  - Header: Zap icon, "自动化", count, "新建自动化".
  - Empty state:
    - Show 4-6 template buttons: 每日摘要, PR Review, Bug Triage, Weekly Report, Dependency Audit, Documentation Check.
    - Template click opens dialog with prefilled title/description/schedule.
  - List columns:
    - Title.
    - Assigned agent.
    - Execution mode: 创建 Issue / 仅运行.
    - Status: active/paused/archived.
    - Trigger summary: frequency/time/timezone or webhook/API.
    - Last run.
    - Actions: 编辑, 手动触发, 暂停/启用, 删除.
  - Create/edit dialog:
    - Title and description/prompt.
    - Agent picker.
    - Output mode segmented control.
    - Schedule section:
      - Frequency: hourly, daily, weekdays, weekly, custom cron.
      - Time input and timezone.
      - Cron preview.
      - Next-run preview when derivable.
    - Trigger type: schedule first; webhook/API can be shown as advanced.
    - Submit creates/updates autopilot then trigger, with partial-failure messaging.
  - Run visibility:
    - If no detail route exists, show last run and manual trigger result inline.
    - Once detail exists, row navigates to detail with run history.

### Issue Detail
- Original Multica flow: editable title/body, comments/timeline, collapsible properties sidebar.
- BodiAgent design:
  - Remove direct HTMX raw JSON swaps from main detail, comments, and activity containers.
  - Load issue JSON and render:
    - Number, title, description, status, priority, assignee, project, labels, dates.
    - Comments with author, timestamp, content.
    - Activity with action, actor, timestamp, detail.
  - Main region:
    - Back link to Issues.
    - Editable title and description.
    - Comment composer with disabled empty submit.
    - Timeline list.
  - Sidebar:
    - Property rows for status, priority, assignee, project, due date, labels, created/updated.
    - Every dropdown sends PATCH and shows saved/error state.
  - Empty/error:
    - If issue fetch fails, show retry and link back.

### Chat
- Original Multica intent: direct agent conversation with live feedback.
- BodiAgent design:
  - Desktop layout: left session rail, right transcript/composer.
  - If session rail is not implemented yet, top agent picker plus "新对话" is acceptable for P0.
  - Transcript:
    - User bubbles right, agent/system bubbles left.
    - Preserve whitespace, escape HTML, show timestamps.
    - Show WebSocket state: connecting, connected, disconnected, failed.
  - Composer:
    - Disabled until agent/session and WebSocket are ready.
    - Enter to send, Shift+Enter newline.
    - On send, append optimistic user message.
  - Empty state:
    - If no agents: link to Agents page.
    - If no session: choose agent and start.
  - Reconnect:
    - Show retry button after close/error; do not silently fail.

### Settings and Tokens
- Original Multica settings flow: predictable settings sections, explicit persistence.
- BodiAgent design:
  - Profile section stays in `/settings/`.
  - Preferences must distinguish local-only theme from backend-persisted language/notifications.
  - Token page:
    - Header: key icon, "CLI Token".
    - Compact create form at top or modal.
    - One-time token reveal in a warning panel with copy button.
    - Token list rows: name, prefix, created, last used/expires if available, revoke.
    - Revoke requires confirmation and removes row after success.

### Workspace, Members, Labels, Skills
- These are currently API-only or not fully templated.
- Do not add fake UI controls until implementation exists.
- When added, use:
  - Settings tabs/sections for Workspace and Members.
  - Dense member rows with role dropdown and remove action.
  - Label manager as small rows with color swatch, name, issue count, edit/delete.
  - Skill manager as list/detail with markdown preview and file attachments.

## UI Completion Roadmap
- Phase 1: Shared surface language.
  - Add reusable classes to `frontend/static/css/app.css`: page header, toolbar, dense table rows, dialog, empty state, alert, property rows.
  - Keep Tailwind CDN utilities as implementation detail; templates should read as shared BodiAgent components.
  - Exit criteria: Agents, Projects, Autopilots, Issue Detail, Chat, and Tokens no longer each invent incompatible spacing/header/form patterns.
- Phase 2: Agents management.
  - Replace desktop card grid with dense management table and mobile stacked rows.
  - Implement create/edit dialog, JSON validation, archive/restore/delete actions, and explicit daemon/prerequisite empty state.
  - Exit criteria: Playwright can create, edit, archive/restore, delete, search/filter, and verify no raw JSON or dead controls.
- Phase 3: Projects management.
  - Convert `/projects/` from creation-first UI to Multica-style list/table plus create/edit dialog.
  - Add inline priority/status controls where serializers allow updates; otherwise make read-only state explicit.
  - Exit criteria: Playwright can create, edit, delete, search/filter, and validate API `title` contract from the browser.
- Phase 4: Autopilots.
  - Add template-driven empty state, list rows, create/edit dialog, schedule/trigger controls, manual run, pause/enable, delete.
  - Keep run result visible inline until an Autopilot detail route exists.
  - Exit criteria: Playwright can create from a template, edit schedule/output mode, manually trigger, pause/enable, and see run status.
- Phase 5: Issue detail rendering.
  - Replace raw JSON swaps with DOM rendering for issue body, comments, activity, and sidebar properties.
  - Add editable title/body, comment composer, saved/error states, and property PATCH controls.
  - Exit criteria: Playwright can open a seeded issue, update properties, add comments, inspect timeline, and assert no DRF JSON appears as page content.
- Phase 6: Chat.
  - Add desktop session rail or P0 top agent/session picker, transcript bubbles, WebSocket state, reconnect, and robust composer behavior.
  - Exit criteria: Playwright can open/create a session, connect WebSocket, send text, receive broadcast across two browsers, escape XSS text, and use mobile chat.
- Phase 7: Settings and tokens.
  - Separate local-only preferences from backend-persisted settings.
  - Complete CLI token creation, one-time reveal/copy, list, and revoke confirmation.
  - Exit criteria: Playwright can generate/copy/revoke a token and verify no full-page raw JSON replacement.
- Phase 8: Browser regression suite.
  - Implement the Playwright suite described in `docs/playwright-e2e-test-plan.md`.
  - Exit criteria: Auth, dashboard, issues, agents, projects, autopilots, inbox, chat, tokens, and 375px responsive smoke pass locally.

## Accessibility
- Target standard: practical WCAG 2.1 AA for P0 flows.
- Keyboard/focus behavior:
  - Every dialog traps focus, closes on Escape, returns focus to opener.
  - Every icon-only button has `aria-label` or visible text.
  - Row actions are reachable by keyboard.
- Contrast/readability:
  - Small text must meet contrast requirements on gray backgrounds.
  - Error/success must not rely only on color.
- Screen-reader semantics:
  - Use semantic `<table>` or list roles for dense rows.
  - Use `aria-live="polite"` for alerts, chat transcript updates, and token generation.
- Reduced motion and sensory considerations:
  - Avoid nonessential animation.

## Responsive behavior
- Supported breakpoints/devices:
  - Desktop primary.
  - 375px mobile smoke for all P0 pages.
- Layout adaptations:
  - Dense tables become stacked rows on mobile.
  - Toolbars wrap into two rows; primary action remains visible.
  - Dialogs become full-width bottom/center panels within viewport height.
  - Project detail sidebar becomes a sheet or collapsible section.
- Touch/hover differences:
  - No action hidden behind hover only.
  - Kebab/action menus must be visible on touch layouts.

## Interaction states
- Loading:
  - Use skeleton row groups for lists and detail pages.
  - Avoid replacing a full page with "加载中..." only.
- Empty:
  - One sentence plus one action.
  - For unavailable prerequisites, show the prerequisite action.
- Error:
  - Inline alert with retry.
  - Preserve user-entered form values.
- Success:
  - Inline toast/alert; update row/list without full reload.
- Disabled:
  - Disable submit when required fields are missing and show why when possible.
- Offline/slow network:
  - Chat shows disconnected state.
  - HTMX/fetch errors show retry and do not leave stale spinners.

## Content voice
- Tone: concise, operational, Chinese-first.
- Terminology:
  - Keep "Issue" in English.
  - Use "智能体" for Agent.
  - Use "工作区" for Workspace.
  - Use "自动化（Autopilot）" or "自动化" consistently, not "自动驾驶".
- Microcopy rules:
  - Buttons use verbs: 创建, 保存, 编辑, 归档, 恢复, 删除, 生成, 撤销.
  - Empty states should say what is missing and what to do next.
  - Destructive confirmations name the object and consequence.

## Implementation constraints
- Framework/styling system:
  - Django Templates, HTMX, Alpine, page-local JavaScript.
  - Do not import React components into BodiAgent.
- Design-token constraints:
  - Current BodiAgent uses Tailwind CDN and gray/blue utilities.
  - Prefer extracting repeated classes into `frontend/static/css/app.css`.
- Performance constraints:
  - Lists should render from API data without blocking full page navigation.
  - Avoid large synchronous DOM rewrites when incremental row updates suffice.
- Compatibility constraints:
  - API responses are DRF JSON.
  - Workspace-scoped API calls require `X-Workspace-ID`.
  - Project create uses `title`.
  - Delete responses return `200 {"ok": true}`.
- Test/screenshot expectations:
  - Playwright must cover no raw JSON, JS console errors, mobile 375px, and every P0 create/edit/delete flow described in this document.

## Open questions
- [ ] Should BodiAgent port Multica design tokens into a local Tailwind config instead of CDN utilities? Owner: frontend. Impact: visual parity and dark mode.
- [ ] Should `/projects/<id>/` and `/autopilots/<id>/` detail routes be added before or after P0 browser tests? Owner: product/frontend. Impact: scope of Project/Autopilot Playwright tests.
- [ ] Which runtime presence fields are available in BodiAgent for Agent availability chips? Owner: backend/frontend. Impact: Agents toolbar fidelity.
- [ ] Are Workspace/member/label/skill management UI in P0 or P1? Owner: product. Impact: settings scope and tests.
