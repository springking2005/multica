"""Factory-boy factories for test data generation."""

import uuid

import factory
from django.contrib.auth import get_user_model
from django.utils import timezone

from accounts.models import Daemon, Member, Workspace
from agents.models import Agent, Task

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("email",)

    id = factory.LazyFunction(uuid.uuid4)
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    name = factory.Faker("name")
    is_active = True


class WorkspaceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Workspace
        django_get_or_create = ("slug",)

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Workspace {n}")
    slug = factory.Sequence(lambda n: f"workspace-{n}")
    issue_prefix = factory.LazyFunction(lambda: "MUL")
    issue_counter = 0
    settings = factory.LazyFunction(dict)
    repos = factory.LazyFunction(list)


class MemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Member

    id = factory.LazyFunction(uuid.uuid4)
    workspace = factory.SubFactory(WorkspaceFactory)
    user = factory.SubFactory(UserFactory)
    role = Member.ROLE_OWNER


class DaemonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Daemon
        django_get_or_create = ("machine_id",)

    id = factory.LazyFunction(uuid.uuid4)
    machine_id = factory.LazyFunction(uuid.uuid4)
    device_name = factory.Faker("word")
    available_providers = factory.LazyFunction(lambda: ["claude"])
    last_heartbeat = factory.LazyFunction(timezone.now)


class AgentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Agent

    id = factory.LazyFunction(uuid.uuid4)
    workspace = factory.SubFactory(WorkspaceFactory)
    daemon = factory.SubFactory(DaemonFactory)
    name = factory.Sequence(lambda n: f"agent-{n}")
    provider = "claude"
    model = "claude-sonnet-4"
    status = Agent.Status.ACTIVE
    visibility = Agent.Visibility.WORKSPACE
    max_concurrent_tasks = 3


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "projects.Project"

    id = factory.LazyFunction(uuid.uuid4)
    workspace = factory.SubFactory(WorkspaceFactory)
    title = factory.Sequence(lambda n: f"Project {n}")
    status = "planned"
    priority = "none"


class IssueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "issues.Issue"

    id = factory.LazyFunction(uuid.uuid4)
    workspace = factory.SubFactory(WorkspaceFactory)
    number = factory.Sequence(lambda n: n + 1)
    title = factory.Sequence(lambda n: f"Issue {n}")
    status = "backlog"
    priority = "none"
    creator_type = "member"
    creator_id = factory.LazyFunction(uuid.uuid4)
    position = 0


class CommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "issues.Comment"

    id = factory.LazyFunction(uuid.uuid4)
    workspace = factory.SubFactory(WorkspaceFactory)
    issue = factory.SubFactory(IssueFactory)
    author_type = "member"
    author_id = factory.LazyFunction(uuid.uuid4)
    content = factory.Faker("sentence")
    type = "comment"


class TaskFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Task

    id = factory.LazyFunction(uuid.uuid4)
    agent = factory.SubFactory(AgentFactory)
    daemon = factory.LazyAttribute(lambda obj: obj.agent.daemon)
    status = Task.Status.QUEUED
    priority = 0
