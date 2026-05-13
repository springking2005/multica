"""Celery configuration — async task scheduling for autopilots."""

import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bodiagent.settings_dev")

app = Celery("bodiagent")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
