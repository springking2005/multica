"""Model creation tests for autopilots app."""

import uuid

import pytest

from accounts.models import Daemon, Workspace
from agents.models import Agent, Task
from autopilots.models import Autopilot, AutopilotRun, AutopilotTrigger
from issues.models import Issue

pytestmark = pytest.mark.django_db


class TestAutopilotModel:
    def test_create_autopilot_minimal(self, workspace, agent):
        ap = Autopilot.objects.create(
            workspace=workspace,
            title="Minimal Autopilot",
            assignee=agent,
            created_by_type="member",
            created_by_id=uuid.uuid4(),
        )
        assert ap.id is not None
        assert isinstance(ap.id, uuid.UUID)
        assert ap.title == "Minimal Autopilot"
        assert ap.description == ""
        assert ap.status == Autopilot.Status.ACTIVE
        assert ap.execution_mode == Autopilot.ExecutionMode.CREATE_ISSUE
        assert ap.issue_title_template == ""
        assert ap.last_run_at is None
        assert ap.created_at is not None
        assert ap.updated_at is not None

    def test_create_autopilot_full(self, workspace, agent):
        ap = Autopilot.objects.create(
            workspace=workspace,
            title="Full Autopilot",
            description="A full autopilot",
            assignee=agent,
            status=Autopilot.Status.PAUSED,
            execution_mode=Autopilot.ExecutionMode.RUN_ONLY,
            issue_title_template="[Auto] {{ title }}",
            created_by_type="member",
            created_by_id=uuid.uuid4(),
        )
        assert ap.title == "Full Autopilot"
        assert ap.description == "A full autopilot"
        assert ap.status == Autopilot.Status.PAUSED
        assert ap.execution_mode == Autopilot.ExecutionMode.RUN_ONLY
        assert ap.issue_title_template == "[Auto] {{ title }}"

    def test_autopilot_str(self, autopilot):
        assert str(autopilot) == "Test Autopilot"

    def test_autopilot_save_updates_updated_at(self, autopilot):
        old_updated = autopilot.updated_at
        autopilot.title = "Updated Title"
        autopilot.save()
        assert autopilot.updated_at > old_updated

    def test_autopilot_cascade_on_workspace_delete(self, workspace, agent):
        ap = Autopilot.objects.create(
            workspace=workspace,
            title="Cascade Test",
            assignee=agent,
            created_by_type="member",
            created_by_id=uuid.uuid4(),
        )
        ap_id = ap.id
        workspace.delete()
        assert not Autopilot.objects.filter(id=ap_id).exists()

    def test_autopilot_cascade_on_agent_delete(self, workspace, agent):
        ap = Autopilot.objects.create(
            workspace=workspace,
            title="Cascade Test",
            assignee=agent,
            created_by_type="member",
            created_by_id=uuid.uuid4(),
        )
        ap_id = ap.id
        agent.delete()
        assert not Autopilot.objects.filter(id=ap_id).exists()

    def test_status_choices(self, autopilot):
        for status in Autopilot.Status.values:
            autopilot.status = status
            autopilot.full_clean()
            autopilot.save()

    def test_execution_mode_choices(self, autopilot):
        for mode in Autopilot.ExecutionMode.values:
            autopilot.execution_mode = mode
            autopilot.full_clean()
            autopilot.save()


class TestAutopilotTriggerModel:
    def test_create_schedule_trigger(self, autopilot):
        trigger = AutopilotTrigger.objects.create(
            autopilot=autopilot,
            kind=AutopilotTrigger.Kind.SCHEDULE,
            cron_expression="0 * * * *",
            label="Hourly",
        )
        assert trigger.id is not None
        assert isinstance(trigger.id, uuid.UUID)
        assert trigger.autopilot == autopilot
        assert trigger.kind == AutopilotTrigger.Kind.SCHEDULE
        assert trigger.cron_expression == "0 * * * *"
        assert trigger.enabled is True
        assert trigger.timezone == "Asia/Shanghai"
        assert trigger.label == "Hourly"
        assert trigger.webhook_token is None

    def test_create_webhook_trigger(self, autopilot):
        trigger = AutopilotTrigger.objects.create(
            autopilot=autopilot,
            kind=AutopilotTrigger.Kind.WEBHOOK,
            webhook_token=uuid.uuid4().hex,
            label="Webhook",
        )
        assert trigger.kind == AutopilotTrigger.Kind.WEBHOOK
        assert trigger.webhook_token is not None
        assert trigger.cron_expression == ""

    def test_create_api_trigger(self, autopilot):
        trigger = AutopilotTrigger.objects.create(
            autopilot=autopilot,
            kind=AutopilotTrigger.Kind.API,
            label="API trigger",
        )
        assert trigger.kind == AutopilotTrigger.Kind.API

    def test_trigger_str(self, schedule_trigger):
        assert "Test Autopilot" in str(schedule_trigger)
        assert "schedule" in str(schedule_trigger)

    def test_trigger_save_updates_updated_at(self, schedule_trigger):
        old = schedule_trigger.updated_at
        schedule_trigger.enabled = False
        schedule_trigger.save()
        assert schedule_trigger.updated_at > old

    def test_trigger_cascade_on_autopilot_delete(self, autopilot):
        trigger = AutopilotTrigger.objects.create(
            autopilot=autopilot,
            kind=AutopilotTrigger.Kind.SCHEDULE,
            cron_expression="* * * * *",
        )
        trigger_id = trigger.id
        autopilot.delete()
        assert not AutopilotTrigger.objects.filter(id=trigger_id).exists()

    def test_kind_choices(self, autopilot):
        for kind in AutopilotTrigger.Kind.values:
            trigger = AutopilotTrigger(
                autopilot=autopilot,
                kind=kind,
            )
            trigger.full_clean()

    def test_timezone_default(self, autopilot):
        trigger = AutopilotTrigger.objects.create(
            autopilot=autopilot,
            kind=AutopilotTrigger.Kind.SCHEDULE,
        )
        assert trigger.timezone == "Asia/Shanghai"


class TestAutopilotRunModel:
    def test_create_run(self, autopilot):
        run = AutopilotRun.objects.create(
            autopilot=autopilot,
            source=AutopilotRun.Source.MANUAL,
        )
        assert run.id is not None
        assert isinstance(run.id, uuid.UUID)
        assert run.autopilot == autopilot
        assert run.source == AutopilotRun.Source.MANUAL
        assert run.status == AutopilotRun.Status.ISSUE_CREATED
        assert run.trigger is None
        assert run.issue is None
        assert run.task is None
        assert run.triggered_at is not None
        assert run.completed_at is None
        assert run.failure_reason == ""
        assert run.trigger_payload == {}
        assert run.result == {}

    def test_create_run_with_trigger(self, autopilot, schedule_trigger):
        run = AutopilotRun.objects.create(
            autopilot=autopilot,
            trigger=schedule_trigger,
            source=AutopilotRun.Source.SCHEDULE,
            status=AutopilotRun.Status.COMPLETED,
        )
        assert run.trigger == schedule_trigger
        assert run.source == AutopilotRun.Source.SCHEDULE
        assert run.status == AutopilotRun.Status.COMPLETED

    def test_run_str(self, autopilot_run):
        assert "Run" in str(autopilot_run)
        assert "completed" in str(autopilot_run)

    def test_run_cascade_on_autopilot_delete(self, autopilot):
        run = AutopilotRun.objects.create(
            autopilot=autopilot,
            source=AutopilotRun.Source.MANUAL,
        )
        run_id = run.id
        autopilot.delete()
        assert not AutopilotRun.objects.filter(id=run_id).exists()

    def test_run_trigger_set_null_on_delete(self, autopilot, schedule_trigger):
        run = AutopilotRun.objects.create(
            autopilot=autopilot,
            trigger=schedule_trigger,
            source=AutopilotRun.Source.SCHEDULE,
        )
        schedule_trigger.delete()
        run.refresh_from_db()
        assert run.trigger is None

    def test_source_choices(self, autopilot):
        for source in AutopilotRun.Source.values:
            run = AutopilotRun(autopilot=autopilot, source=source)
            run.full_clean()

    def test_status_choices(self, autopilot):
        for status in AutopilotRun.Status.values:
            run = AutopilotRun(autopilot=autopilot, source=AutopilotRun.Source.MANUAL)
            run.status = status
            run.full_clean()

    def test_run_with_issue(self, autopilot, workspace):
        issue = Issue.objects.create(
            workspace=workspace,
            title="Test Issue",
            creator_type="member",
            creator_id=uuid.uuid4(),
        )
        run = AutopilotRun.objects.create(
            autopilot=autopilot,
            source=AutopilotRun.Source.MANUAL,
            issue=issue,
        )
        assert run.issue == issue

    def test_run_with_task(self, autopilot, agent):
        task = Task.objects.create(
            agent=agent,
            status=Task.Status.QUEUED,
        )
        run = AutopilotRun.objects.create(
            autopilot=autopilot,
            source=AutopilotRun.Source.MANUAL,
            task=task,
        )
        assert run.task == task
