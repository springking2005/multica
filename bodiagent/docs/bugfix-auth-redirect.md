# BugFix: Auth Redirect After Login/Register

**Date**: 2026-05-13
**Branch**: `feature/zh-cn`
**Status**: Fixed, verified

## Problem

After login or register via the web form, the browser displayed raw JSON instead of redirecting to the dashboard. Users could not progress from the auth page to the app.

## Root Cause (3 layers)

### Layer 1 — HTMX not loaded on guest pages
`base_guest.html` did not include the HTMX library, but both `login.html` and `register.html` used `hx-post` on their forms. HTMX attributes were silently ignored — the form fell back to a regular `method="post"` submission targeting the JSON API directly.

### Layer 2 — No Django session created
`accounts/views.py` `login()` and `register()` authenticated the user but never called `django.contrib.auth.login(request, user)`. The API returned JWT tokens but no `sessionid` cookie. Since the dashboard view uses `@login_required` (which checks Django session auth), even if the browser were redirected, the user would still be unauthenticated.

### Layer 3 — No client-side redirect on success
No JavaScript handled the successful API response to redirect the browser. The browser just rendered the JSON payload.

## Changes Made

### 1. `accounts/views.py` — Create Django session on auth

```diff
-from django.contrib.auth import get_user_model
+from django.contrib.auth import get_user_model, login as auth_login

 def register(request):
     ...
     user = serializer.save()
+    auth_login(request, user)
     return Response(...)

 def login(request):
     ...
     user = serializer.validated_data["user"]
+    auth_login(request, user)
     return Response(...)
```

### 2. `frontend/templates/base_guest.html` — Load HTMX

```diff
 <script src="https://cdn.tailwindcss.com"></script>
+<script src="https://unpkg.com/htmx.org@2.0.4"></script>
```

### 3. `frontend/templates/accounts/login.html` — HTMX event + redirect

- Gave the form `id="login-form"`
- Added `hx-swap="innerHTML"` so errors target the `#error` div cleanly
- Fixed form action URLs: removed trailing slash (`/api/auth/login` not `/api/auth/login/`)
- Added JS that listens for `htmx:afterRequest`, parses the JSON response, stores tokens in `localStorage`, and redirects to `/dashboard/`

### 4. `frontend/templates/accounts/register.html` — Same pattern

Same changes as login: form `id`, `hx-swap`, trailing slash fix, JS redirect on 201.

## Verification

```bash
# 1. Login page loads HTMX
curl -s http://localhost:8000/login/ | grep htmx

# 2. Login API sets session cookie
curl -s -D - -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@bodiagentteam.com","password":"admin123"}' \
  | grep sessionid

# 3. Dashboard accessible with session
curl -o /dev/null -w "%{http_code}" http://localhost:8000/dashboard/ \
  -H "Cookie: sessionid=<value>"
# → 200
```

## Test Account

| Field | Value |
|-------|-------|
| Email | `admin@bodiagentteam.com` |
| Password | `admin123` |

## Related

- Dev verification code: `888888` (bypasses email in dev mode)
- Auth URLs use no trailing slash: `/api/auth/login`, `/api/auth/register`
- Tokens stored in `localStorage` keys: `bodiagent_token`, `bodiagent_refresh`

## Follow-up Fix (2026-05-13): `evt.detail.target` vs `evt.detail.elt`

After the initial fix, login still displayed raw JSON. Root cause: the JS event listener used the wrong HTMX event property.

In `htmx:afterRequest`:
- `evt.detail.elt` = the element that triggered the request (the form, id="login-form")
- `evt.detail.target` = the swap target element (the `hx-target`, id="error")

The guard `evt.detail.target.id !== 'login-form'` was **always true** because the swap target is `#error` (id="error"), not the form. The redirect code never ran.

### Fix

`login.html:18` and `register.html:20` — changed:
```diff
-    if (evt.detail.target.id !== 'login-form') return;
+    if (evt.detail.elt.id !== 'login-form') return;
```

### Test guard

`test_manual_login.py` now asserts `evt.detail.elt.id` is present in the login page source, preventing regression.
