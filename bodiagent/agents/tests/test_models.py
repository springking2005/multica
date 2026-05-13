"""Model creation tests for agents app."""

import uuid
from datetime import date

import pytest
from django.utils import timezone

from accounts.models import Daemon, User, Workspace
from agents.models import (
    Agent,
    AgentSkill,
    Skill,
    SkillFile,
    Task,
    TaskMessage,
    TaskUsage,
    TaskUsageDaily,
    TaskUsageDailyDirty,
    TaskUsageRollupState,
)


@pytest.fixture
def workspace() -> Workspace:
    slug = f"test-{uuid.uuid4().hex[:8]}"
    return Workspace.objects.create(name="Test Workspace", slug=slug)


@pytest.fixture
def user() -> User:
    return User.objects.create_user(
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        password="password",
        name="Test User",
    )


@pytest.fixture
def daemon() -> Daemon:
    return Daemon.objects.create(machine_id=uuid.uuid4(), device_name="test-daemon")


@pytest.fixture
def agent(workspace: Workspace, daemon: Daemon, user: User) -> Agent:
    return Agent.objects.create(
        workspace=workspace,
        daemon=daemon,
        owner=user,
        name="Test Agent",
        provider=Agent.Provider.CLAUDE,
        model="claude-sonnet-4-20250514",
        instructions="You are a helpful assistant.",
    )


@pytest.fixture
def skill(workspace: Workspace) -> Skill:
    return Skill.objects.create(
        workspace=workspace,
        name="test-skill",
        description="A test skill",
        content="print('hello')",
    )


@pytest.mark.django_db
class TestAgentModel:
    def test_create_agent_minimal(self, workspace, daemon):
        agent = Agent.objects.create(
            workspace=workspace,
            daemon=daemon,
            name="Minimal Agent",
            provider=Agent.Provider.CLAUDE,
        )
        assert agent.id is not None
        assert isinstance(agent.id, uuid.UUID)
        assert agent.name == "Minimal Agent"
        assert agent.description == ""
        assert agent.provider == Agent.Provider.CLAUDE
        assert agent.status == Agent.Status.ACTIVE
        assert agent.visibility == Agent.Visibility.WORKSPACE
        assert agent.max_concurrent_tasks == 3
        assert agent.custom_env == {}
        assert agent.custom_args == {}
        assert agent.mcp_config == {}
        assert agent.created_at is not None
        assert agent.updated_at is not None

    def test_create_agent_full(self, workspace, daemon, user):
        agent = Agent.objects.create(
            workspace=workspace,
            daemon=daemon,
            owner=user,
            name="Full Agent",
            description="A fully configured agent",
            provider=Agent.Provider.CODEX,
            model="codex-pro",
            instructions="Be precise.",
            max_concurrent_tasks=5,
            status=Agent.Status.ACTIVE,
            visibility=Agent.Visibility.PRIVATE,
            custom_env={"DEBUG": "true"},
            custom_args=["--verbose"],
            mcp_config={"servers": []},
        )
        assert agent.provider == Agent.Provider.CODEX
        assert agent.model == "codex-pro"
        assert agent.max_concurrent_tasks == 5
        assert agent.visibility == Agent.Visibility.PRIVATE
        assert agent.custom_env == {"DEBUG": "true"}
        assert agent.custom_args == ["--verbose"]

    def test_agent_str(self, agent):
        assert str(agent) == "Test Agent"

    def test_agent_provider_choices(self, workspace, daemon):
        agent = Agent.objects.create(
            workspace=workspace,
            daemon=daemon,
            name="Provider Test",
            provider=Agent.Provider.CLAUDE,
        )
        for provider in Agent.Provider.values:
            agent.provider = provider
            agent.full_clean()
            agent.save()

    def test_agent_status_choices(self, agent):
        for status_val in Agent.Status.values:
            agent.status = status_val
            agent.full_clean()
            agent.save()

    def test_agent_visibility_choices(self, agent):
        for visibility_val in Agent.Visibility.values:
            agent.visibility = visibility_val
            agent.full_clean()
            agent.save()

    def test_agent_unique_name_per_workspace(self, workspace, daemon):
        Agent.objects.create(workspace=workspace, daemon=daemon, name="Unique", provider=Agent.Provider.CLAUDE)
        with pytest.raises(Exception):
            Agent.objects.create(workspace=workspace, daemon=daemon, name="Unique", provider=Agent.Provider.CLAUDE)

    def test_agent_archive_restore(self, agent):
        agent.status = Agent.Status.ARCHIVED
        agent.save()
        assert agent.status == Agent.Status.ARCHIVED

        agent.status = Agent.Status.ACTIVE
        agent.save()
        assert agent.status == Agent.Status.ACTIVE

    def test_agent_daemon_set_null(self, agent, daemon):
        agent_id = agent.id
        daemon.delete()
        agent.refresh_from_db()
        assert agent.daemon is None


@pytest.mark.django_db
class TestTaskModel:
    def test_create_task_minimal(self, agent):
        task = Task.objects.create(agent=agent, daemon=agent.daemon)
        assert task.id is not None
        assert isinstance(task.id, uuid.UUID)
        assert task.status == Task.Status.QUEUED
        assert task.priority == 0
        assert task.attempt == 1
        assert task.max_attempts == 1
        assert task.force_fresh_session is False
        assert task.result == {}
        assert task.created_at is not None

    def test_create_task_with_fields(self, agent):
        task = Task.objects.create(
            agent=agent,
            daemon=agent.daemon,
            priority=5,
            session_id="session-123",
            work_dir="/tmp/work",
            trigger_summary="Triggered by cron",
            force_fresh_session=True,
            max_attempts=3,
        )
        assert task.priority == 5
        assert task.session_id == "session-123"
        assert task.work_dir == "/tmp/work"
        assert task.trigger_summary == "Triggered by cron"
        assert task.force_fresh_session is True
        assert task.max_attempts == 3

    def test_task_str(self, agent):
        task = Task.objects.create(agent=agent, daemon=agent.daemon)
        assert str(task).startswith("Task ")
        assert "[queued]" in str(task)

    def test_task_status_choices(self, agent):
        task = Task.objects.create(agent=agent, daemon=agent.daemon)
        for status_val in Task.Status.values:
            task.status = status_val
            task.full_clean()
            task.save()

    def test_task_lifecycle(self, agent):
        task = Task.objects.create(agent=agent, daemon=agent.daemon)
        assert task.status == Task.Status.QUEUED

        task.status = Task.Status.DISPATCHED
        task.save()
        assert task.status == Task.Status.DISPATCHED

        task.status = Task.Status.RUNNING
        task.started_at = timezone.now()
        task.save()
        assert task.status == Task.Status.RUNNING
        assert task.started_at is not None

        task.status = Task.Status.COMPLETED
        task.completed_at = timezone.now()
        task.result = {"summary": "Done"}
        task.save()
        assert task.status == Task.Status.COMPLETED
        assert task.completed_at is not None
        assert task.result == {"summary": "Done"}

    def test_task_parent_child(self, agent):
        parent = Task.objects.create(agent=agent, daemon=agent.daemon)
        child = Task.objects.create(
            agent=agent, daemon=agent.daemon, parent_task=parent
        )
        assert child.parent_task == parent
        assert list(parent.sub_tasks.all()) == [child]

    def test_task_cascade_delete(self, agent):
        task = Task.objects.create(agent=agent, daemon=agent.daemon)
        task_id = task.id
        agent.delete()
        assert not Task.objects.filter(id=task_id).exists()

    def test_task_indexes(self, agent):
        task = Task.objects.create(agent=agent, daemon=agent.daemon, status=Task.Status.QUEUED)
        results = list(
            Task.objects.filter(daemon=agent.daemon, status=Task.Status.QUEUED)
        )
        assert task in results

        results = list(
            Task.objects.filter(agent=agent, status=Task.Status.QUEUED)
        )
        assert task in results


@pytest.mark.django_db
class TestTaskMessageModel:
    def test_create_message(self, agent):
        task = Task.objects.create(agent=agent, daemon=agent.daemon)
        msg = TaskMessage.objects.create(
            task=task,
            seq=1,
            type=TaskMessage.Type.TEXT,
            content="Hello world",
        )
        assert msg.id is not None
        assert msg.seq == 1
        assert msg.type == TaskMessage.Type.TEXT
        assert msg.content == "Hello world"
        assert msg.created_at is not None

    def test_create_tool_message(self, agent):
        task = Task.objects.create(agent=agent, daemon=agent.daemon)
        msg = TaskMessage.objects.create(
            task=task,
            seq=2,
            type=TaskMessage.Type.TOOL_USE,
            tool="read_file",
            input={"path": "/tmp/test.txt"},
            metadata={"duration_ms": 150},
        )
        assert msg.type == TaskMessage.Type.TOOL_USE
        assert msg.tool == "read_file"
        assert msg.input == {"path": "/tmp/test.txt"}

    def test_message_ordering(self, agent):
        task = Task.objects.create(agent=agent, daemon=agent.daemon)
        msg3 = TaskMessage.objects.create(task=task, seq=3, type="text")
        msg1 = TaskMessage.objects.create(task=task, seq=1, type="text")
        msg2 = TaskMessage.objects.create(task=task, seq=2, type="text")
        messages = list(TaskMessage.objects.filter(task=task))
        assert messages[0].seq <= messages[1].seq <= messages[2].seq

    def test_message_cascade_delete(self, agent):
        task = Task.objects.create(agent=agent, daemon=agent.daemon)
        msg = TaskMessage.objects.create(task=task, seq=1, type="text")
        msg_id = msg.id
        task.delete()
        assert not TaskMessage.objects.filter(id=msg_id).exists()


@pytest.mark.django_db
class TestTaskUsageModel:
    def test_create_usage(self, agent):
        task = Task.objects.create(agent=agent, daemon=agent.daemon)
        usage = TaskUsage.objects.create(
            task=task,
            provider="claude",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=200,
            cache_read_tokens=50,
            cache_write_tokens=10,
            cost=0.015,
        )
        assert usage.id is not None
        assert usage.input_tokens == 100
        assert usage.output_tokens == 200
        assert usage.cost == 0.015
        assert usage.cache_read_tokens == 50
        assert usage.cache_write_tokens == 10

    def test_usage_unique_per_task_provider_model(self, agent):
        task = Task.objects.create(agent=agent, daemon=agent.daemon)
        TaskUsage.objects.create(
            task=task, provider="claude", model="opus", input_tokens=10, output_tokens=20
        )
        with pytest.raises(Exception):
            TaskUsage.objects.create(
                task=task, provider="claude", model="opus", input_tokens=30, output_tokens=40
            )

    def test_usage_cascade_delete(self, agent):
        task = Task.objects.create(agent=agent, daemon=agent.daemon)
        usage = TaskUsage.objects.create(
            task=task, provider="gemini", model="gemini-pro",
            input_tokens=10, output_tokens=20,
        )
        usage_id = usage.id
        task.delete()
        assert not TaskUsage.objects.filter(id=usage_id).exists()


@pytest.mark.django_db
class TestTaskUsageDailyModel:
    def test_create_daily(self, workspace, daemon, agent):
        daily = TaskUsageDaily.objects.create(
            workspace=workspace,
            daemon=daemon,
            agent=agent,
            provider="claude",
            model="opus",
            bucket_date=date.today(),
            total_input_tokens=1000,
            total_output_tokens=2000,
            total_cost=15.50,
        )
        assert daily.id is not None
        assert daily.total_input_tokens == 1000
        assert daily.bucket_date == date.today()

    def test_daily_unique(self, workspace, daemon, agent):
        TaskUsageDaily.objects.create(
            workspace=workspace,
            daemon=daemon,
            agent=agent,
            provider="claude",
            model="opus",
            bucket_date=date.today(),
        )
        with pytest.raises(Exception):
            TaskUsageDaily.objects.create(
                workspace=workspace,
                daemon=daemon,
                agent=agent,
                provider="claude",
                model="opus",
                bucket_date=date.today(),
            )


@pytest.mark.django_db
class TestTaskUsageRollupStateModel:
    def test_create_rollup_state(self):
        state = TaskUsageRollupState.objects.create(
            last_processed_at=timezone.now()
        )
        assert state.id is not None
        assert state.last_processed_at is not None

    def test_multiple_rollup_states(self):
        s1 = TaskUsageRollupState.objects.create(last_processed_at=timezone.now())
        s2 = TaskUsageRollupState.objects.create(last_processed_at=timezone.now())
        assert s1.id != s2.id


@pytest.mark.django_db
class TestTaskUsageDailyDirtyModel:
    def test_create_dirty(self):
        task_uuid = uuid.uuid4()
        dirty = TaskUsageDailyDirty.objects.create(task_id=task_uuid)
        assert dirty.id is not None
        assert dirty.task_id == task_uuid

    def test_task_id_is_uuid(self):
        task_uuid = uuid.uuid4()
        dirty = TaskUsageDailyDirty.objects.create(task_id=task_uuid)
        dirty.refresh_from_db()
        assert str(dirty.task_id) == str(task_uuid)


@pytest.mark.django_db
class TestSkillModel:
    def test_create_skill_minimal(self, workspace):
        skill = Skill.objects.create(workspace=workspace, name="my-skill")
        assert skill.id is not None
        assert skill.name == "my-skill"
        assert skill.description == ""
        assert skill.content == ""
        assert skill.config == {}
        assert skill.created_at is not None
        assert skill.updated_at is not None

    def test_create_skill_full(self, workspace):
        skill = Skill.objects.create(
            workspace=workspace,
            name="full-skill",
            description="A complete skill",
            content="import os\nos.system('hello')",
            config={"version": 1},
            created_by_type="member",
            created_by_id=uuid.uuid4(),
        )
        assert skill.description == "A complete skill"
        assert skill.content == "import os\nos.system('hello')"
        assert skill.config == {"version": 1}
        assert skill.created_by_type == "member"

    def test_skill_str(self, workspace):
        skill = Skill.objects.create(workspace=workspace, name="str-skill")
        assert str(skill).startswith("str-skill")

    def test_skill_unique_name_per_workspace(self, workspace):
        Skill.objects.create(workspace=workspace, name="unique-skill")
        with pytest.raises(Exception):
            Skill.objects.create(workspace=workspace, name="unique-skill")


@pytest.mark.django_db
class TestSkillFileModel:
    def test_create_skill_file(self, workspace):
        skill = Skill.objects.create(workspace=workspace, name="file-skill")
        sf = SkillFile.objects.create(
            skill=skill, path="README.md", content="# Hello"
        )
        assert sf.id is not None
        assert sf.path == "README.md"
        assert sf.content == "# Hello"

    def test_skill_file_unique(self, workspace):
        skill = Skill.objects.create(workspace=workspace, name="unique-file")
        SkillFile.objects.create(skill=skill, path="main.py", content="x=1")
        with pytest.raises(Exception):
            SkillFile.objects.create(skill=skill, path="main.py", content="x=2")

    def test_skill_file_cascade_delete(self, workspace):
        skill = Skill.objects.create(workspace=workspace, name="cascade-file")
        sf = SkillFile.objects.create(skill=skill, path="test.py", content="pass")
        sf_id = sf.id
        skill.delete()
        assert not SkillFile.objects.filter(id=sf_id).exists()


@pytest.mark.django_db
class TestAgentSkillModel:
    def test_create_agent_skill(self, agent, skill):
        ag_skill = AgentSkill.objects.create(agent=agent, skill=skill)
        assert ag_skill is not None
        assert ag_skill.agent == agent
        assert ag_skill.skill == skill

    def test_agent_skill_unique(self, agent, skill):
        AgentSkill.objects.create(agent=agent, skill=skill)
        with pytest.raises(Exception):
            AgentSkill.objects.create(agent=agent, skill=skill)

    def test_agent_skill_cascade_on_agent(self, agent, skill):
        AgentSkill.objects.create(agent=agent, skill=skill)
        agent_id = agent.id
        agent.delete()
        assert not AgentSkill.objects.filter(agent_id=agent_id).exists()

    def test_agent_skill_cascade_on_skill(self, agent, skill):
        AgentSkill.objects.create(agent=agent, skill=skill)
        skill_id = skill.id
        skill.delete()
        assert not AgentSkill.objects.filter(skill_id=skill_id).exists()
