"""Autopilot service layer — evaluate triggers, create runs, dispatch agent tasks."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone as dt_timezone

from celery import shared_task
from django.db import transaction

try:
    from croniter import croniter
except ImportError:
    croniter = None
from django.utils import timezone

from .models import Autopilot, AutopilotRun, AutopilotTrigger


class AutopilotService:
    """Business logic for autopilot trigger evaluation and run creation."""

    @staticmethod
    def evaluate_triggers(
        autopilot: Autopilot,
    ) -> list[AutopilotTrigger]:
        """Find triggers that should fire now."""
        due_triggers = []
        now = timezone.now()
        for trigger in autopilot.triggers.filter(
            enabled=True,
            kind=AutopilotTrigger.Kind.SCHEDULE,
        ):
            if trigger.next_run_at and trigger.next_run_at <= now:
                due_triggers.append(trigger)
        return due_triggers

    @staticmethod
    def create_run(
        autopilot: Autopilot,
        trigger: AutopilotTrigger | None = None,
        source: str = AutopilotRun.Source.MANUAL,
        trigger_payload: dict | None = None,
    ) -> AutopilotRun:
        """Create an AutopilotRun and optionally create an issue/task."""
        run = AutopilotRun.objects.create(
            autopilot=autopilot,
            trigger=trigger,
            source=source,
            status=AutopilotRun.Status.ISSUE_CREATED,
            trigger_payload=trigger_payload or {},
        )

        if trigger is not None:
            trigger.last_fired_at = timezone.now()
            trigger.save(update_fields=["last_fired_at", "updated_at"])

        autopilot.last_run_at = timezone.now()
        autopilot.save(update_fields=["last_run_at", "updated_at"])

        return run

    @staticmethod
    def compute_next_run_at(
        trigger: AutopilotTrigger,
    ) -> datetime | None:
        """Compute the next run time from a cron expression."""
        if not trigger.cron_expression or croniter is None:
            return None
        try:
            tz = dt_timezone.utc  # simplified; Django stores aware datetimes
            base = timezone.now()
            cron = croniter(trigger.cron_expression, base)
            return cron.get_next(datetime)
        except (ValueError, KeyError):
            return None

    @staticmethod
    def update_next_run(trigger: AutopilotTrigger) -> None:
        """Update next_run_at on a schedule trigger after firing."""
        if trigger.kind == AutopilotTrigger.Kind.SCHEDULE:
            trigger.next_run_at = AutopilotService.compute_next_run_at(trigger)
            trigger.save(update_fields=["next_run_at", "updated_at"])

    @staticmethod
    def create_issue_for_run(
        run: AutopilotRun,
    ) -> None:
        """Create an issue from the autopilot's template if execution_mode is create_issue."""
        autopilot = run.autopilot
        if autopilot.execution_mode != Autopilot.ExecutionMode.CREATE_ISSUE:
            return

        from issues.models import Issue

        title = autopilot.issue_title_template or autopilot.title
        issue = Issue.objects.create(
            workspace=autopilot.workspace,
            title=title,
            description=autopilot.description or "",
            assignee_type="agent",
            assignee_id=autopilot.assignee_id,
            creator_type=autopilot.created_by_type,
            creator_id=autopilot.created_by_id,
            origin_type=Issue.OriginType.AUTOPILOT,
            origin_id=autopilot.id,
        )
        run.issue = issue
        run.status = AutopilotRun.Status.ISSUE_CREATED
        run.save(update_fields=["issue", "status"])

    @staticmethod
    def dispatch_task(run: AutopilotRun) -> None:
        """Dispatch an agent task for the autopilot run."""
        from agents.models import Task

        autopilot = run.autopilot
        task = Task.objects.create(
            agent=autopilot.assignee,
            status=Task.Status.QUEUED,
            priority=0,
            autopilot_run_id=run.id,
            trigger_summary=autopilot.title,
        )
        run.task = task
        run.status = AutopilotRun.Status.RUNNING
        run.save(update_fields=["task", "status"])


@shared_task
def evaluate_scheduled_autopilots() -> None:
    """Celery periodic task: evaluate all schedule triggers and create runs."""
    now = timezone.now()
    due_triggers = AutopilotTrigger.objects.filter(
        enabled=True,
        kind=AutopilotTrigger.Kind.SCHEDULE,
        next_run_at__lte=now,
    ).select_related("autopilot")

    for trigger in due_triggers:
        with transaction.atomic():
            run = AutopilotService.create_run(
                autopilot=trigger.autopilot,
                trigger=trigger,
                source=AutopilotRun.Source.SCHEDULE,
            )
            AutopilotService.update_next_run(trigger)
            AutopilotService.create_issue_for_run(run)
            AutopilotService.dispatch_task(run)
