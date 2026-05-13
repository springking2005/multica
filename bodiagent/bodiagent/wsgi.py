"""WSGI config — HTTP only, no WebSocket."""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bodiagent.settings_prod")
application = get_wsgi_application()
