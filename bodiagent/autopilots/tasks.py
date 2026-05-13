"""Celery tasks for autopilot scheduling."""

from __future__ import annotations

from celery import shared_task

from .services import evaluate_scheduled_autopilots


@shared_task
def evaluate_autopilots_task() -> None:
    """Periodic task to evaluate all scheduled autopilot triggers."""
    evaluate_scheduled_autopilots()
