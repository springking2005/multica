"""API verification test v3 — with fixes applied, unique test data."""
import json, django, os, uuid
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bodiagent.settings_dev')
django.setup()

from django.test import Client

c = Client()
results = []

def test(name, response, expected_status=200):
    try:
        body = json.loads(response.content.decode())
    except:
        body = response.content.decode()[:300]
    status_ok = response.status_code == expected_status
    flag = "PASS" if status_ok else "FAIL"
    msg = f"[{flag}] {name} (status={response.status_code}, expected={expected_status})"
    results.append(msg)
    print(msg)
    if not status_ok or expected_status == 201:
        snippet = json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else str(body)
        print(f"      Body: {snippet[:300]}")
    return body, response

# Unique suffix to avoid slug collisions
uid = uuid.uuid4().hex[:8]
print(f"Test run ID: {uid}")
print("=" * 70)
print("波笛智能体 API 综合验证 (v3)")
print("=" * 70)

# ── Auth ──
resp = c.get("/health/")
test("1. Health check", resp)

resp = c.post("/api/auth/register", json.dumps({
    "email": f"test_{uid}@test.com",
    "password": "test123456",
    "name": f"Tester{uid}"
}), content_type="application/json")
reg, _ = test("2. Register", resp, expected_status=201)

resp = c.post("/api/auth/login", json.dumps({
    "email": f"test_{uid}@test.com",
    "password": "test123456"
}), content_type="application/json")
login, _ = test("3. Login", resp)
token = login.get("token")
refresh = login.get("refresh")
auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

resp = c.post("/api/auth/verify-code", json.dumps({
    "email": f"test_{uid}@test.com",
    "code": "888888"
}), content_type="application/json")
test("4. Verify Code", resp)

if refresh:
    resp = c.post("/api/auth/token-refresh", json.dumps({"refresh": refresh}), content_type="application/json")
    test("5. Token Refresh", resp)

resp = c.get("/api/me", **auth)
test("6. Get Me", resp)

# ── Workspace ──
unique_slug = f"TST{uid.upper()}"
resp = c.post("/api/workspaces/", json.dumps({
    "name": f"TestWS {uid}",
    "slug": unique_slug
}), content_type="application/json", **auth)
ws, _ = test("7. Create Workspace", resp, expected_status=201)
ws_id = ws.get("id")
print(f"      WS ID: {ws_id} | Slug: {unique_slug}")

resp = c.get("/api/workspaces/", **auth)
ws_list, _ = test("8. List Workspaces", resp)
print(f"      Count: {len(ws_list.get('results', []))}")

# ── Workspace-scoped endpoints ──
ws_hdr = {**auth, "HTTP_X_WORKSPACE_ID": str(ws_id)}

resp = c.get("/api/issues", **ws_hdr)
test("9. List Issues (empty)", resp)

resp = c.post("/api/issues", json.dumps({
    "title": "Test Issue from API",
    "description": "Testing API"
}), content_type="application/json", **ws_hdr)
issue, _ = test("10. Create Issue", resp, expected_status=201)
issue_id = issue.get("id")

if issue_id:
    resp = c.get(f"/api/issues/{issue_id}", **ws_hdr)
    test("11. Get Issue", resp)

    resp = c.patch(f"/api/issues/{issue_id}", json.dumps({
        "title": "Updated Issue"
    }), content_type="application/json", **ws_hdr)
    test("12. Update Issue", resp)

    resp = c.post(f"/api/issues/{issue_id}/comments", json.dumps({
        "content": "Test comment"
    }), content_type="application/json", **ws_hdr)
    cmt, _ = test("13. Add Comment", resp, expected_status=201)

    resp = c.get(f"/api/issues/{issue_id}/comments", **ws_hdr)
    test("14. List Comments", resp)

    resp = c.get(f"/api/issues?search=Test", **ws_hdr)
    test("15. Search Issues", resp)

# ── Agents ──
resp = c.get("/api/agents", **ws_hdr)
test("16. List Agents (empty)", resp)

# Create a daemon first (needed for agent with daemon_id)
resp = c.post("/api/daemon/register", json.dumps({
    "machine_id": str(uuid.uuid4()),
    "device_name": f"test-device-{uid}",
}), content_type="application/json")
dmn, _ = test("17. Daemon Register", resp, expected_status=201)
daemon_id = dmn.get("id")
print(f"      daemon_id: {daemon_id}")

resp = c.post("/api/agents", json.dumps({
    "name": f"TestAgent {uid}",
    "provider": "claude",
    "daemon_id": str(daemon_id) if daemon_id else str(uuid.uuid4()),
}), content_type="application/json", **ws_hdr)
agent, _ = test("18. Create Agent", resp, expected_status=201)
agent_id = agent.get("id")

if agent_id:
    resp = c.get("/api/agents", **ws_hdr)
    test("19. List Agents", resp)

    resp = c.get(f"/api/agents/{agent_id}/tasks", **ws_hdr)
    test("20. Get Agent Tasks (empty)", resp)

    resp = c.post("/api/tasks/queue", json.dumps({
        "agent_id": str(agent_id),
    }), content_type="application/json", **ws_hdr)
    task, _ = test("21. Queue Task", resp, expected_status=201)
    task_id = task.get("id")

    if task_id:
        resp = c.get(f"/api/daemon/tasks/{task_id}/status", **ws_hdr)
        test("22. Task Status", resp)

        resp = c.post(f"/api/tasks/{task_id}/cancel", json.dumps({}), content_type="application/json", **ws_hdr)
        test("23. Cancel Task", resp)

# ── Inbox ──
resp = c.get("/api/inbox", **ws_hdr)
test("24. List Inbox", resp)

resp = c.get("/api/activities", **ws_hdr)
test("25. List Activities", resp)

resp = c.get("/api/pins", **ws_hdr)
test("26. List Pins", resp)

# ── Projects ──
resp = c.get("/api/projects", **ws_hdr)
test("27. List Projects (empty)", resp)

resp = c.post("/api/projects", json.dumps({
    "title": f"TestProject {uid}",
    "key": f"TP{uid[:4].upper()}"
}), content_type="application/json", **ws_hdr)
proj, _ = test("28. Create Project", resp, expected_status=201)
proj_id = proj.get("id")

# ── CLI Token ──
resp = c.post("/api/tokens/cli-token/", json.dumps({}), content_type="application/json", **auth)
test("29. CLI Token", resp)

# ── Logout ──
resp = c.post("/api/auth/logout", json.dumps({"refresh": refresh}), content_type="application/json", **auth)
test("30. Logout", resp)

# ── Cleanup ──
if issue_id:
    resp = c.delete(f"/api/issues/{issue_id}", **ws_hdr)
    test("31. Delete Issue", resp)

if agent_id:
    resp = c.delete(f"/api/agents/{agent_id}", **ws_hdr)
    test("32. Delete Agent", resp)

if proj_id:
    resp = c.delete(f"/api/projects/{proj_id}", **ws_hdr)
    test("33. Delete Project", resp)

# ── Summary ──
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
passed = sum(1 for r in results if r.startswith("[PASS]"))
failed = sum(1 for r in results if r.startswith("[FAIL]"))
for r in results:
    if r.startswith("[FAIL]"):
        print(r)
print(f"Total: {len(results)} | PASS: {passed} | FAIL: {failed}")
