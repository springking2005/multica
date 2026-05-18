"""End-to-end tests that simulate manual browser login/register flow.

These tests use Django's test Client (not APIClient) to verify the full
request-response cycle: page load → credentials POST → session cookie → redirect
→ authenticated page access.  They are the closest CI approximation of a human
opening a browser.
"""

import pytest
from django.contrib.auth import get_user_model

User = get_user_model()
pytestmark = pytest.mark.django_db

# ── helpers ──────────────────────────────────────────────────────────────


def _create_user(email="test@bodiagentteam.com", password="testpass123", name="Tester"):
    return User.objects.create_user(email=email, password=password, name=name)


def _login_page(client):
    return client.get("/login/")


def _login_api(client, email, password):
    return client.post(
        "/api/auth/login",
        {"email": email, "password": password},
        content_type="application/json",
    )


def _register_api(client, email, password, name="New User"):
    return client.post(
        "/api/auth/register",
        {"email": email, "password": password, "name": name},
        content_type="application/json",
    )


# ── login page (GET) ─────────────────────────────────────────────────────


class TestLoginPage:
    def test_page_loads_200(self, client):
        r = client.get("/login/")
        assert r.status_code == 200

    def test_page_contains_form(self, client):
        r = client.get("/login/")
        content = r.content.decode()
        assert 'method="post"' in content
        assert 'name="email"' in content
        assert 'name="password"' in content

    def test_page_has_htmx_loaded(self, client):
        """HTMX on the guest base is required for hx-post to function."""
        r = client.get("/login/")
        content = r.content.decode()
        assert "htmx.org@2.0.4" in content

    def test_page_has_csrf_token(self, client):
        r = client.get("/login/")
        assert "csrftoken" in r.cookies

    def test_page_has_login_form_id(self, client):
        """The form id is used by our redirect JS event listener."""
        r = client.get("/login/")
        content = r.content.decode()
        assert 'id="login-form"' in content

    def test_authenticated_user_redirected_from_root(self, client):
        """Root view redirects authenticated users to dashboard, anonymous to login."""
        # Anonymous → login
        r_anon = client.get("/", follow=False)
        assert r_anon.status_code == 302
        assert r_anon["Location"] == "/login/"

        # Authenticated → dashboard
        user = _create_user()
        client.force_login(user)
        r_auth = client.get("/", follow=False)
        assert r_auth.status_code == 302
        assert r_auth["Location"] == "/dashboard/"


# ── login API (POST) ─────────────────────────────────────────────────────


class TestLoginApi:
    def test_valid_credentials_returns_200(self, client):
        _create_user()
        r = _login_api(client, "test@bodiagentteam.com", "testpass123")
        assert r.status_code == 200

    def test_valid_credentials_returns_token_and_refresh(self, client):
        _create_user()
        r = _login_api(client, "test@bodiagentteam.com", "testpass123")
        data = r.json()
        assert data["token"]
        assert data["refresh"]

    def test_valid_credentials_returns_user_object(self, client):
        _create_user()
        r = _login_api(client, "test@bodiagentteam.com", "testpass123")
        data = r.json()
        assert data["user"]["email"] == "test@bodiagentteam.com"
        assert data["user"]["name"] == "Tester"

    def test_valid_credentials_sets_session_cookie(self, client):
        """Login must create a Django session so @login_required views work."""
        _create_user()
        r = _login_api(client, "test@bodiagentteam.com", "testpass123")
        assert "sessionid" in r.cookies

    def test_session_cookie_is_httponly(self, client):
        _create_user()
        r = _login_api(client, "test@bodiagentteam.com", "testpass123")
        cookie = r.cookies["sessionid"]
        assert "httponly" in str(cookie).lower()

    def test_wrong_password_returns_400(self, client):
        _create_user()
        r = _login_api(client, "test@bodiagentteam.com", "wrongpass")
        assert r.status_code == 400
        assert "error" in r.json() or "detail" in r.json() or "Invalid" in str(r.content)

    def test_wrong_password_no_session_cookie(self, client):
        _create_user()
        r = _login_api(client, "test@bodiagentteam.com", "wrongpass")
        assert "sessionid" not in r.cookies

    def test_nonexistent_user_returns_400(self, client):
        r = _login_api(client, "noone@bodiagentteam.com", "whatever")
        assert r.status_code == 400

    def test_missing_email_returns_400(self, client):
        r = client.post(
            "/api/auth/login",
            {"password": "testpass123"},
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_missing_password_returns_400(self, client):
        r = client.post(
            "/api/auth/login",
            {"email": "test@bodiagentteam.com"},
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_empty_body_returns_400(self, client):
        r = client.post("/api/auth/login", "{}", content_type="application/json")
        assert r.status_code == 400

    def test_both_json_and_form_content_types_accepted(self, client):
        """DRF default parsers include both JSONParser and FormParser."""
        _create_user()
        r_json = client.post(
            "/api/auth/login",
            {"email": "test@bodiagentteam.com", "password": "testpass123"},
            content_type="application/json",
        )
        assert r_json.status_code == 200

        r_form = client.post(
            "/api/auth/login",
            "email=test@bodiagentteam.com&password=testpass123",
            content_type="application/x-www-form-urlencoded",
        )
        assert r_form.status_code == 200

    def test_email_case_insensitive(self, client):
        _create_user()
        r = _login_api(client, "Test@BodiAgentTeam.com", "testpass123")
        assert r.status_code == 200
        assert r.json()["user"]["email"] == "test@bodiagentteam.com"


# ── dashboard access after login ─────────────────────────────────────────


class TestDashboardAfterLogin:
    def test_dashboard_accessible_after_login(self, client):
        _create_user()
        login_r = _login_api(client, "test@bodiagentteam.com", "testpass123")
        assert "sessionid" in login_r.cookies

        # Pass session cookie to dashboard request
        session_cookie = login_r.cookies["sessionid"]
        client.cookies["sessionid"] = session_cookie.value
        r = client.get("/dashboard/")
        assert r.status_code == 200

    def test_dashboard_blocked_without_session(self, client):
        r = client.get("/dashboard/")
        assert r.status_code == 302
        assert "login" in r["Location"]

    def test_dashboard_contains_welcome_message(self, client):
        _create_user()
        login_r = _login_api(client, "test@bodiagentteam.com", "testpass123")
        client.cookies["sessionid"] = login_r.cookies["sessionid"].value
        r = client.get("/dashboard/")
        content = r.content.decode()
        assert "Tester" in content or "test@bodiagentteam.com" in content

    def test_dashboard_contains_issue_button(self, client):
        _create_user()
        login_r = _login_api(client, "test@bodiagentteam.com", "testpass123")
        client.cookies["sessionid"] = login_r.cookies["sessionid"].value
        r = client.get("/dashboard/")
        content = r.content.decode()
        assert "创建 Issue" in content or "issues/" in content


# ── full manual flow simulation ──────────────────────────────────────────


class TestFullManualLoginFlow:
    """Simulate exactly what a human does in a browser."""

    def test_login_form_has_correct_hx_attributes(self, client):
        """The real form submits via HTMX; check wiring is in place."""
        r = client.get("/login/")
        content = r.content.decode()
        assert 'hx-post="/api/auth/login"' in content
        assert 'hx-target="#error"' in content
        assert 'id="login-form"' in content
        # redirect script references dashboard
        assert "/dashboard/" in content
        # JS listener must use evt.detail.elt (trigger element), not
        # evt.detail.target (swap target = #error div).  See bugfix-auth-redirect.md.
        assert "evt.detail.elt.id" in content
        assert "evt.detail.elt.id !== 'login-form'" in content

    def test_complete_login_json_flow(self, client):
        """Full flow using JSON content-type (API consumers, daemon CLI)."""
        _create_user()

        r1 = client.get("/login/")
        assert r1.status_code == 200
        assert "htmx.org@2.0.4" in r1.content.decode()

        r2 = client.post(
            "/api/auth/login",
            {"email": "test@bodiagentteam.com", "password": "testpass123"},
            content_type="application/json",
        )
        assert r2.status_code == 200
        data = r2.json()
        assert data["token"]
        assert data["refresh"]
        assert "sessionid" in r2.cookies

        client.cookies["sessionid"] = r2.cookies["sessionid"].value
        r3 = client.get("/dashboard/")
        assert r3.status_code == 200

        r4 = client.get("/issues/")
        assert r4.status_code == 200

        r5 = client.get("/agents/")
        assert r5.status_code == 200

    def test_complete_login_form_encoded_flow(self, client):
        """Full flow using form-encoded submission — matches what the real
        browser HTMX form sends.  This is the path that protects against
        regressions in form encoding, hx wiring, and redirect logic."""
        _create_user()

        # Step 1 — load login page, grab CSRF token
        r1 = client.get("/login/")
        assert r1.status_code == 200
        csrf = r1.cookies.get("csrftoken", "")

        # Step 2 — submit form-encoded (exactly like the HTML form + hx-post)
        r2 = client.post(
            "/api/auth/login",
            "email=test@bodiagentteam.com&password=testpass123",
            content_type="application/x-www-form-urlencoded",
            HTTP_X_CSRFTOKEN=csrf.value if hasattr(csrf, "value") else csrf,
        )
        assert r2.status_code == 200
        data = r2.json()
        assert data["token"]
        assert data["refresh"]
        assert "sessionid" in r2.cookies

        # Step 3 — session cookie is automatically set by test Client
        r3 = client.get("/dashboard/")
        assert r3.status_code == 200
        content = r3.content.decode()
        assert ("Tester" in content) or ("test@bodiagentteam.com" in content)

    def test_login_shared_client(self, client):
        """Django test Client persists cookies across requests automatically."""
        _create_user()
        client.get("/login/")
        r = _login_api(client, "test@bodiagentteam.com", "testpass123")
        assert r.status_code == 200
        r = client.get("/dashboard/")
        assert r.status_code == 200


# ── register page (GET) ──────────────────────────────────────────────────


class TestRegisterPage:
    def test_page_loads_200(self, client):
        r = client.get("/register/")
        assert r.status_code == 200

    def test_page_contains_form(self, client):
        r = client.get("/register/")
        content = r.content.decode()
        assert 'method="post"' in content
        assert 'name="email"' in content
        assert 'name="password"' in content
        assert 'name="name"' in content

    def test_page_has_htmx_loaded(self, client):
        r = client.get("/register/")
        assert "htmx.org@2.0.4" in r.content.decode()

    def test_page_has_form_id(self, client):
        r = client.get("/register/")
        assert 'id="register-form"' in r.content.decode()


# ── register API (POST) ──────────────────────────────────────────────────


class TestRegisterApi:
    def test_valid_registration_returns_201(self, client):
        r = _register_api(client, "newuser@bodiagentteam.com", "newpass123")
        assert r.status_code == 201

    def test_valid_registration_creates_user(self, client):
        r = _register_api(client, "newuser@bodiagentteam.com", "newpass123")
        assert r.status_code == 201
        assert User.objects.filter(email="newuser@bodiagentteam.com").exists()

    def test_valid_registration_returns_token(self, client):
        r = _register_api(client, "newuser@bodiagentteam.com", "newpass123")
        data = r.json()
        assert data["token"]
        assert data["refresh"]

    def test_valid_registration_sets_session_cookie(self, client):
        r = _register_api(client, "newuser@bodiagentteam.com", "newpass123")
        assert "sessionid" in r.cookies

    def test_duplicate_email_is_accepted_or_rejected(self, client):
        """get_or_create semantics: registering with an existing email may
        either return the existing user or an error.  Either is acceptable."""
        _create_user(email="dup@bodiagentteam.com")
        r = _register_api(client, "dup@bodiagentteam.com", "newpass123")
        # The register serializer uses get_or_create, so it will return
        # 201 with the existing user rather than 400.
        assert r.status_code == 201

    def test_register_then_dashboard(self, client):
        r1 = _register_api(client, "newuser2@bodiagentteam.com", "newpass123")
        assert r1.status_code == 201
        assert "sessionid" in r1.cookies

        client.cookies["sessionid"] = r1.cookies["sessionid"].value
        r2 = client.get("/dashboard/")
        assert r2.status_code == 200

    def test_missing_email_returns_400(self, client):
        r = client.post(
            "/api/auth/register",
            {"password": "newpass123", "name": "X"},
            content_type="application/json",
        )
        assert r.status_code == 400

    def test_empty_body_returns_400(self, client):
        r = client.post("/api/auth/register", "{}", content_type="application/json")
        assert r.status_code == 400


# ── full manual register → login flow ────────────────────────────────────


class TestFullManualRegisterFlow:
    def test_register_then_logout_then_login(self, client):
        email = "roundtrip@bodiagentteam.com"
        password = "roundtrip123"

        # Register
        r1 = _register_api(client, email, password)
        assert r1.status_code == 201

        # Logout
        r2 = client.post(
            "/api/auth/logout",
            {"refresh": r1.json()["refresh"]},
            content_type="application/json",
        )
        assert r2.status_code == 200

        # Login again
        r3 = _login_api(client, email, password)
        assert r3.status_code == 200
        assert "sessionid" in r3.cookies


# ── auth API contract (JWT + session shape) ──────────────────────────────


class TestAuthResponseContract:
    """Ensure the response shape consumers (frontend JS, daemon CLI) depend on
    does not drift."""

    def test_login_response_keys(self, client):
        _create_user()
        r = _login_api(client, "test@bodiagentteam.com", "testpass123")
        data = r.json()
        assert set(data.keys()) == {"token", "refresh", "user"}

    def test_login_user_object_keys(self, client):
        _create_user()
        r = _login_api(client, "test@bodiagentteam.com", "testpass123")
        user = r.json()["user"]
        required = {"id", "email", "name", "onboarding_completed"}
        assert required <= set(user.keys())

    def test_token_is_non_empty_string(self, client):
        _create_user()
        r = _login_api(client, "test@bodiagentteam.com", "testpass123")
        assert isinstance(r.json()["token"], str)
        assert len(r.json()["token"]) > 0

    def test_refresh_is_non_empty_string(self, client):
        _create_user()
        r = _login_api(client, "test@bodiagentteam.com", "testpass123")
        assert isinstance(r.json()["refresh"], str)
        assert len(r.json()["refresh"]) > 0


def test_login_page_has_non_htmx_fallback_script(client):
    """If HTMX fails to load, the login form must not submit as plain HTML."""
    response = client.get("/login/")
    content = response.content.decode()

    assert 'id="login-form"' in content
    assert "preventDefault" in content
    assert "fetch(form.action" in content
    assert "credentials: 'same-origin'" in content
