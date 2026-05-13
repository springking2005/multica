"""Shared middleware for 波笛智能体."""

import logging
import time

from django.conf import settings
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("bodiagent")


class WorkspaceContextMiddleware:
    """Extract workspace from request path or header and attach to request.

    Workspace-scoped URLs are of the form /<slug>/... where slug matches
    a Workspace.slug. The resolved workspace_id is attached to the request
    so downstream views don't need to re-query.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.workspace_id = None  # type: ignore[attr-defined]
        request.workspace_slug = None  # type: ignore[attr-defined]

        # Resolve from X-Workspace-ID header (API clients / daemon)
        if ws_id := request.headers.get("X-Workspace-ID"):
            request.workspace_id = ws_id  # type: ignore[attr-defined]

        return self.get_response(request)


class RequestLoggingMiddleware:
    """Log request method, path, status, and duration."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = (time.monotonic() - start) * 1000

        if not request.path.startswith("/static/") and not request.path.startswith("/health"):
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 1),
                },
            )

        return response
