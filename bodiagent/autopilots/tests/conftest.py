"""Fixtures for autopilot tests."""

import uuid

import pytest

from accounts.models import Daemon, Workspace
from agents.models import Agent
from autopilots.models import Autopilot, AutopilotRun, AutopilotTrigger


@pytest.fixture
def workspace() -> Workspace:
    slug = f"test-{uuid.uuid4().hex[:8]}"
    return Workspace.objects.create(name="Test Workspace", slug=slug)


@pytest.fixture
def daemon() -> Daemon:
    return Daemon.objects.create(machine_id=uuid.uuid4())


@pytest.fixture
def agent(workspace: Workspace) -> Agent:
    return Agent.objects.create(
        workspace=workspace,
        name="Test Agent",
        provider=Agent.Provider.CLAUDE,
    )


@pytest.fixture
def autopilot(workspace: Workspace, agent: Agent) -> Autopilot:
    return Autopilot.objects.create(
        workspace=workspace,
        title="Test Autopilot",
        assignee=agent,
        created_by_type="member",
        created_by_id=uuid.uuid4(),
    )


@pytest.fixture
def schedule_trigger(autopilot: Autopilot) -> AutopilotTrigger:
    return AutopilotTrigger.objects.create(
        autopilot=autopilot,
        kind=AutopilotTrigger.Kind.SCHEDULE,
        cron_expression="0 9 * * *",
        label="Daily at 9am",
    )


@pytest.fixture
def webhook_trigger(autopilot: Autopilot) -> AutopilotTrigger:
    return AutopilotTrigger.objects.create(
        autopilot=autopilot,
        kind=AutopilotTrigger.Kind.WEBHOOK,
        webhook_token=uuid.uuid4().hex,
        label="GitHub webhook",
    )


@pytest.fixture
def autopilot_run(autopilot: Autopilot) -> AutopilotRun:
    return AutopilotRun.objects.create(
        autopilot=autopilot,
        source=AutopilotRun.Source.MANUAL,
        status=AutopilotRun.Status.COMPLETED,
    )
