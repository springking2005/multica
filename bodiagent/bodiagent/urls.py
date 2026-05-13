"""Root URL configuration for 波笛智能体."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

from . import views_frontend

urlpatterns = [
    # Health
    path("health/", lambda r: __import__("django").http.HttpResponse("OK")),
    path("admin/", admin.site.urls),

    # ── Frontend shell (template-serving routes) ──────────────────────
    path("", views_frontend.home, name="home"),
    path("login/", TemplateView.as_view(template_name="accounts/login.html"), name="accounts-login"),
    path("register/", TemplateView.as_view(template_name="accounts/register.html"), name="accounts-register"),
    path("dashboard/", login_required(TemplateView.as_view(template_name="accounts/dashboard.html")), name="dashboard"),
    path("issues/", login_required(TemplateView.as_view(template_name="issues/board.html")), name="issues-board"),
    path(
        "issues/<uuid:issue_id>/",
        views_frontend.issue_detail,
        name="issues-detail",
    ),
    path("chat/", login_required(views_frontend.chat_detail), name="chat-new"),
    path("chat/<uuid:session_id>/", login_required(views_frontend.chat_detail), name="chat-detail"),
    path("agents/", login_required(views_frontend.agents), name="agents-list"),
    path("projects/", login_required(views_frontend.projects), name="projects-list"),
    path("autopilots/", login_required(views_frontend.autopilots), name="autopilots-list"),
    path("inbox/", login_required(TemplateView.as_view(template_name="inbox/list.html")), name="inbox-list"),
    path("settings/", login_required(TemplateView.as_view(template_name="settings/profile.html")), name="settings-profile"),
    path("settings/tokens/", login_required(views_frontend.tokens), name="settings-tokens"),

    # ── API routes ────────────────────────────────────────────────────
    path("auth/", include("accounts.urls_auth")),
    path("api/auth/", include("accounts.urls_auth", namespace="accounts_auth_compat")),
    path("api/", include("accounts.urls")),
    path("api/", include("issues.urls")),
    path("api/", include("agents.urls")),
    path("api/", include("inbox.urls")),
    path("api/", include("chat.urls")),
    path("api/", include("projects.urls")),
    path("api/", include("autopilots.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
