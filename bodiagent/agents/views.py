"""Agent, Task, Skill, and Daemon control plane API views."""

from __future__ import annotations

from uuid import UUID

from django.db import models
from django.db.models import QuerySet
from django.http import Http404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.workspace_scope import (
    resolve_daemon_from_request,
    resolve_workspace_id,
    resolve_workspace_member,
    validate_daemon_binding,
    validate_request_daemon_id,
    validate_skill_ids,
)

from .models import (
    Agent,
    AgentSkill,
    Skill,
    SkillFile,
    Task,
    TaskMessage,
    TaskUsage,
    TaskUsageDaily,
)
from .serializers import (
    AgentCreateSerializer,
    AgentSerializer,
    AgentUpdateSerializer,
    DaemonTaskClaimSerializer,
    SetAgentSkillsSerializer,
    SkillFileBatchSerializer,
    SkillFileSerializer,
    SkillImportSerializer,
    SkillSerializer,
    TaskClaimSerializer,
    TaskCompleteSerializer,
    TaskFailSerializer,
    TaskMessageBatchSerializer,
    TaskMessageSerializer,
    TaskProgressSerializer,
    TaskQueueSerializer,
    TaskSerializer,
    TaskUsageSerializer,
)
from .services import complete_task_with_result


class WorkspaceScopedMixin:
    """Resolve workspace scope and enforce membership."""

    request: Request

    def get_workspace_id(self) -> UUID:
        return resolve_workspace_id(self.request)



# ── Agent ViewSet ──────────────────────────────────────────────────────


class AgentViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    """CRUD, archive, restore, and skill management for agents."""

    lookup_url_kwarg = "agent_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self) -> QuerySet[Agent]:
        return Agent.objects.filter(workspace_id=self.get_workspace_id())

    def get_serializer_class(self):
        if self.action == "create":
            return AgentCreateSerializer
        if self.action in {"update", "partial_update"}:
            return AgentUpdateSerializer
        return AgentSerializer

    def perform_create(self, serializer):
        workspace_id = self.get_workspace_id()
        daemon = None
        daemon_id = serializer.validated_data.pop("daemon_id", None)
        if daemon_id:
            daemon = validate_daemon_binding(daemon_id, workspace_id)
        skill_ids = serializer.validated_data.get("skill_ids", [])
        validate_skill_ids(skill_ids, workspace_id)
        serializer.save(workspace_id=workspace_id, daemon=daemon, owner=self.request.user)

    def perform_update(self, serializer):
        daemon = None
        daemon_id = serializer.validated_data.pop("daemon_id", None)
        if daemon_id:
            daemon = validate_daemon_binding(daemon_id, self.get_workspace_id())
        kwargs = {"daemon": daemon} if daemon_id is not None else {}
        serializer.save(**kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({"ok": True})

    @action(detail=True, methods=["post"])
    def archive(self, request, agent_id=None):
        agent = self.get_object()
        agent.status = Agent.Status.ARCHIVED
        agent.save(update_fields=["status", "updated_at"])
        return Response(AgentSerializer(agent).data)

    @action(detail=True, methods=["post"])
    def restore(self, request, agent_id=None):
        agent = self.get_object()
        agent.status = Agent.Status.ACTIVE
        agent.save(update_fields=["status", "updated_at"])
        return Response(AgentSerializer(agent).data)

    @action(detail=True, methods=["get", "put"])
    def skills(self, request, agent_id=None):
        agent = self.get_object()
        if request.method == "GET":
            skill_ids = AgentSkill.objects.filter(agent=agent).values_list(
                "skill_id", flat=True
            )
            skills = Skill.objects.filter(id__in=skill_ids)
            return Response(SkillSerializer(skills, many=True).data)

        serializer = SetAgentSkillsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agent_skills = set(
            AgentSkill.objects.filter(agent=agent).values_list("skill_id", flat=True)
        )
        desired_skills = set(serializer.validated_data["skill_ids"])
        validate_skill_ids(list(desired_skills), agent.workspace_id)
        to_add = desired_skills - agent_skills
        to_remove = agent_skills - desired_skills

        for skill_id in to_add:
            AgentSkill.objects.get_or_create(agent=agent, skill_id=skill_id)
        if to_remove:
            AgentSkill.objects.filter(agent=agent, skill_id__in=to_remove).delete()

        return Response({"ok": True})

    @action(detail=True, methods=["post"], url_path="cancel-tasks")
    def cancel_tasks(self, request, agent_id=None):
        agent = self.get_object()
        cancelled_count = Task.objects.filter(
            agent=agent,
            status__in=(Task.Status.QUEUED, Task.Status.DISPATCHED, Task.Status.RUNNING),
        ).update(status=Task.Status.CANCELLED, updated_at=timezone.now())
        return Response({"ok": True, "cancelled": cancelled_count})

    @action(detail=True, methods=["get"])
    def tasks(self, request, agent_id=None):
        agent = self.get_object()
        queryset = Task.objects.filter(agent=agent).order_by("-created_at")
        serializer = TaskSerializer(queryset, many=True)
        return Response(serializer.data)


# ── Task ViewSet ───────────────────────────────────────────────────────


class TaskViewSet(WorkspaceScopedMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Task lifecycle: queue, dispatch, claim, progress, complete, fail, cancel."""

    lookup_url_kwarg = "task_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Task]:
        return Task.objects.filter(
            agent__workspace_id=self.get_workspace_id()
        )

    @action(detail=False, methods=["post"])
    def queue(self, request):
        serializer = TaskQueueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace_id = self.get_workspace_id()
        try:
            agent = Agent.objects.get(
                id=serializer.validated_data["agent_id"],
                workspace_id=workspace_id,
            )
        except Agent.DoesNotExist as exc:
            raise Http404("Agent not found") from exc

        issue_id = serializer.validated_data.get("issue_id")
        if issue_id:
            from issues.models import Issue

            if not Issue.objects.filter(id=issue_id, workspace_id=workspace_id).exists():
                raise ValidationError({"issue_id": "Issue must belong to the workspace."})

        trigger_comment_id = serializer.validated_data.get("trigger_comment_id")
        if trigger_comment_id:
            from issues.models import Comment

            if not Comment.objects.filter(id=trigger_comment_id, workspace_id=workspace_id).exists():
                raise ValidationError({"trigger_comment_id": "Comment must belong to the workspace."})

        autopilot_run_id = serializer.validated_data.get("autopilot_run_id")
        if autopilot_run_id:
            from autopilots.models import AutopilotRun

            if not AutopilotRun.objects.filter(id=autopilot_run_id, autopilot__workspace_id=workspace_id).exists():
                raise ValidationError({"autopilot_run_id": "Autopilot run must belong to the workspace."})

        parent_task_id = serializer.validated_data.get("parent_task_id")
        if parent_task_id and not Task.objects.filter(id=parent_task_id, agent__workspace_id=workspace_id).exists():
            raise ValidationError({"parent_task_id": "Parent task must belong to the workspace."})

        task = Task.objects.create(
            agent=agent,
            daemon=agent.daemon,
            issue_id=issue_id,
            priority=serializer.validated_data.get("priority", 0),
            trigger_summary=serializer.validated_data.get("trigger_summary", ""),
            trigger_comment_id=trigger_comment_id,
            autopilot_run_id=autopilot_run_id,
            parent_task_id=parent_task_id,
            force_fresh_session=serializer.validated_data.get(
                "force_fresh_session", False
            ),
            max_attempts=serializer.validated_data.get("max_attempts", 1),
        )
        return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="dispatch")
    def dispatch_task(self, request, task_id=None):
        task = self.get_object()
        if task.status != Task.Status.QUEUED:
            raise ValidationError({"status": "Only queued tasks can be dispatched."})
        task.status = Task.Status.DISPATCHED
        task.save(update_fields=["status", "updated_at"])
        return Response(TaskSerializer(task).data)

    @action(detail=False, methods=["post"])
    def claim(self, request):
        serializer = TaskClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace_id = self.get_workspace_id()
        daemon = validate_daemon_binding(serializer.validated_data["daemon_id"], workspace_id, required=True)

        task = (
            Task.objects.filter(
                daemon=daemon,
                agent__workspace_id=workspace_id,
                status=Task.Status.QUEUED,
            )
            .order_by("-priority", "created_at")
            .first()
        )
        if task is None:
            return Response(
                {"detail": "No pending tasks for this daemon."},
                status=status.HTTP_404_NOT_FOUND,
            )
        task.status = Task.Status.DISPATCHED
        if serializer.validated_data.get("session_id"):
            task.session_id = serializer.validated_data["session_id"]
        if serializer.validated_data.get("work_dir"):
            task.work_dir = serializer.validated_data["work_dir"]
        task.save(update_fields=["status", "session_id", "work_dir", "updated_at"])
        return Response(DaemonTaskClaimSerializer(task).data)

    @action(detail=True, methods=["post"])
    def progress(self, request, task_id=None):
        task = self.get_object()
        if task.status not in (Task.Status.DISPATCHED, Task.Status.RUNNING):
            raise ValidationError(
                {"status": "Can only report progress on dispatched or running tasks."}
            )
        serializer = TaskProgressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if task.status == Task.Status.DISPATCHED:
            task.status = Task.Status.RUNNING
            if task.started_at is None:
                task.started_at = timezone.now()
        task.last_heartbeat_at = timezone.now()
        task.save(
            update_fields=["status", "started_at", "last_heartbeat_at", "updated_at"]
        )

        TaskMessage.objects.create(
            task=task,
            seq=serializer.validated_data.get("seq", 0),
            type=serializer.validated_data.get("type", "status"),
            content=serializer.validated_data.get("content", ""),
            metadata=serializer.validated_data.get("metadata", {}),
        )
        return Response(TaskSerializer(task).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, task_id=None):
        raise ValidationError({"detail": "Tasks can only be completed by the bound daemon."})

    @action(detail=True, methods=["post"])
    def fail(self, request, task_id=None):
        task = self.get_object()
        if task.status not in (Task.Status.DISPATCHED, Task.Status.RUNNING):
            raise ValidationError({"status": "Only dispatched or running tasks can be failed."})
        serializer = TaskFailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task.status = Task.Status.FAILED
        task.failure_reason = serializer.validated_data.get("failure_reason", "")
        task.completed_at = timezone.now()
        task.save(
            update_fields=["status", "failure_reason", "completed_at", "updated_at"]
        )
        return Response(TaskSerializer(task).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, task_id=None):
        task = self.get_object()
        if task.status not in (
            Task.Status.QUEUED,
            Task.Status.DISPATCHED,
            Task.Status.RUNNING,
        ):
            raise ValidationError({"status": "Only active tasks can be cancelled."})
        task.status = Task.Status.CANCELLED
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at", "updated_at"])
        return Response(TaskSerializer(task).data)

    @action(detail=True, methods=["get", "post"])
    def messages(self, request, task_id=None):
        task = self.get_object()
        if request.method == "GET":
            queryset = TaskMessage.objects.filter(task=task).order_by("seq")
            serializer = TaskMessageSerializer(queryset, many=True)
            return Response(serializer.data)

        serializer = TaskMessageBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        last_seq = (
            TaskMessage.objects.filter(task=task)
            .aggregate(max_seq=models.Max("seq"))["max_seq"]
            or 0
        )
        created = []
        for i, msg in enumerate(serializer.validated_data["messages"]):
            seq = msg.get("seq", last_seq + i + 1)
            created.append(
                TaskMessage(
                    task=task,
                    seq=seq,
                    type=msg.get("type", "text"),
                    tool=msg.get("tool", ""),
                    input=msg.get("input") or {},
                    output=msg.get("output") or {},
                    content=msg.get("content", ""),
                    metadata=msg.get("metadata") or {},
                )
            )
        TaskMessage.objects.bulk_create(created)
        return Response({"ok": True, "count": len(created)})


# ── DaemonControlView ──────────────────────────────────────────────────


class DaemonControlView(APIView):
    """Daemon-scoped task claiming and lifecycle endpoints."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        """Claim a task by daemon_id."""
        serializer = TaskClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        daemon = resolve_daemon_from_request(request)
        validate_request_daemon_id(request, daemon)

        task = (
            Task.objects.filter(
                daemon=daemon,
                status=Task.Status.QUEUED,
            )
            .select_related("agent", "issue")
            .order_by("-priority", "created_at")
            .first()
        )
        if task is None:
            return Response(
                {"detail": "No pending tasks for this daemon."},
                status=status.HTTP_404_NOT_FOUND,
            )
        task.status = Task.Status.DISPATCHED
        if serializer.validated_data.get("session_id"):
            task.session_id = serializer.validated_data["session_id"]
        if serializer.validated_data.get("work_dir"):
            task.work_dir = serializer.validated_data["work_dir"]
        task.save(update_fields=["status", "session_id", "work_dir", "updated_at"])
        return Response(DaemonTaskClaimSerializer(task).data)


class DaemonTaskLifecycleView(viewsets.ViewSet):
    """Daemon-scoped task lifecycle endpoints that do not require workspace headers."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get_task(self, request, task_id: UUID) -> Task:
        daemon = resolve_daemon_from_request(request)
        try:
            return Task.objects.select_related("agent", "issue").get(id=task_id, daemon=daemon)
        except Task.DoesNotExist as exc:
            raise ValidationError({"task_id": "Task not found."}) from exc

    def post_start(self, request, task_id: UUID):
        task = self.get_task(request, task_id)
        if task.status not in (Task.Status.DISPATCHED, Task.Status.RUNNING):
            raise ValidationError({"status": "Can only start dispatched or running tasks."})
        if task.status == Task.Status.DISPATCHED:
            task.status = Task.Status.RUNNING
        if task.started_at is None:
            task.started_at = timezone.now()
        task.last_heartbeat_at = timezone.now()
        task.save(update_fields=["status", "started_at", "last_heartbeat_at", "updated_at"])
        return Response(TaskSerializer(task).data)

    def post_progress(self, request, task_id: UUID):
        task = self.get_task(request, task_id)
        if task.status not in (Task.Status.DISPATCHED, Task.Status.RUNNING):
            raise ValidationError({"status": "Can only report progress on dispatched or running tasks."})
        serializer = TaskProgressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if task.status == Task.Status.DISPATCHED:
            task.status = Task.Status.RUNNING
            if task.started_at is None:
                task.started_at = timezone.now()
        task.last_heartbeat_at = timezone.now()
        task.save(update_fields=["status", "started_at", "last_heartbeat_at", "updated_at"])
        TaskMessage.objects.create(
            task=task,
            seq=serializer.validated_data.get("seq", 0),
            type=serializer.validated_data.get("type", "status"),
            content=serializer.validated_data.get("content", ""),
            metadata=serializer.validated_data.get("metadata", {}),
        )
        return Response(TaskSerializer(task).data)

    def post_complete(self, request, task_id: UUID):
        task = self.get_task(request, task_id)
        serializer = TaskCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        complete_task_with_result(
            task,
            result=serializer.validated_data.get("result", {}),
            branch_name=serializer.validated_data.get("branch_name", ""),
        )
        return Response(TaskSerializer(task).data)

    def post_fail(self, request, task_id: UUID):
        task = self.get_task(request, task_id)
        if task.status not in (Task.Status.DISPATCHED, Task.Status.RUNNING):
            raise ValidationError({"status": "Only dispatched or running tasks can be failed."})
        serializer = TaskFailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task.status = Task.Status.FAILED
        task.failure_reason = serializer.validated_data.get("failure_reason", "")
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "failure_reason", "completed_at", "updated_at"])
        return Response(TaskSerializer(task).data)

    def get_status(self, request, task_id: UUID):
        return Response(TaskSerializer(self.get_task(request, task_id)).data)

    def get_messages(self, request, task_id: UUID):
        task = self.get_task(request, task_id)
        queryset = TaskMessage.objects.filter(task=task).order_by("seq")
        return Response(TaskMessageSerializer(queryset, many=True).data)

    def post_messages(self, request, task_id: UUID):
        task = self.get_task(request, task_id)
        serializer = TaskMessageBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        last_seq = TaskMessage.objects.filter(task=task).aggregate(max_seq=models.Max("seq"))["max_seq"] or 0
        created = []
        for i, msg in enumerate(serializer.validated_data["messages"]):
            seq = msg.get("seq", last_seq + i + 1)
            created.append(
                TaskMessage(
                    task=task,
                    seq=seq,
                    type=msg.get("type", "text"),
                    tool=msg.get("tool", ""),
                    input=msg.get("input") or {},
                    output=msg.get("output") or {},
                    content=msg.get("content", ""),
                    metadata=msg.get("metadata") or {},
                )
            )
        TaskMessage.objects.bulk_create(created)
        return Response({"ok": True, "count": len(created)})

    def post_session(self, request, task_id: UUID):
        task = self.get_task(request, task_id)
        session_id = request.data.get("session_id", "")
        if not session_id:
            raise ValidationError({"session_id": "This field is required."})
        task.session_id = session_id
        task.save(update_fields=["session_id", "updated_at"])
        return Response(TaskSerializer(task).data)

    def post_usage(self, request, task_id: UUID):
        task = self.get_task(request, task_id)
        provider = request.data.get("provider")
        model = request.data.get("model") or "unknown"
        if not provider:
            raise ValidationError({"provider": "This field is required."})
        usage, _ = TaskUsage.objects.update_or_create(
            task=task,
            provider=provider,
            model=model,
            defaults={
                "input_tokens": request.data.get("input_tokens", 0),
                "output_tokens": request.data.get("output_tokens", 0),
                "cache_read_tokens": request.data.get("cache_read_tokens", 0),
                "cache_write_tokens": request.data.get("cache_write_tokens", 0),
                "cost": request.data.get("cost", 0.0),
            },
        )
        return Response(TaskUsageSerializer(usage).data, status=status.HTTP_201_CREATED)


# ── SkillViewSet ───────────────────────────────────────────────────────


class SkillViewSet(WorkspaceScopedMixin, viewsets.ModelViewSet):
    """CRUD, file management, and import for skills."""

    lookup_url_kwarg = "skill_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    serializer_class = SkillSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Skill]:
        return Skill.objects.filter(workspace_id=self.get_workspace_id())

    def perform_create(self, serializer):
        workspace_id = self.get_workspace_id()
        member = resolve_workspace_member(self.request, workspace_id)
        serializer.save(workspace_id=workspace_id, created_by_type="member", created_by_id=member.id)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response({"ok": True})

    @action(detail=True, methods=["get", "put"])
    def files(self, request, skill_id=None):
        skill = self.get_object()
        if request.method == "GET":
            queryset = SkillFile.objects.filter(skill=skill)
            return Response(SkillFileSerializer(queryset, many=True).data)

        serializer = SkillFileBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_data = serializer.validated_data["files"]
        existing_paths = set(
            SkillFile.objects.filter(skill=skill).values_list("path", flat=True)
        )
        new_paths = {f["path"] for f in file_data}

        to_delete = existing_paths - new_paths
        if to_delete:
            SkillFile.objects.filter(skill=skill, path__in=to_delete).delete()

        for item in file_data:
            SkillFile.objects.update_or_create(
                skill=skill,
                path=item["path"],
                defaults={"content": item.get("content", "")},
            )

        return Response({"ok": True})

    @action(detail=False, methods=["post"])
    def import_skill(self, request):
        serializer = SkillImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workspace_id = self.get_workspace_id()
        member = resolve_workspace_member(self.request, workspace_id)
        skill = Skill.objects.create(
            workspace_id=workspace_id,
            created_by_type="member",
            created_by_id=member.id,
            name=serializer.validated_data["name"],
            description=serializer.validated_data.get("description", ""),
            content=serializer.validated_data.get("content", ""),
            config=serializer.validated_data.get("config", {}),
        )
        for item in serializer.validated_data.get("files", []):
            SkillFile.objects.create(
                skill=skill,
                path=item["path"],
                content=item.get("content", ""),
            )
        return Response(SkillSerializer(skill).data, status=status.HTTP_201_CREATED)


# ── TaskUsage ViewSets ─────────────────────────────────────────────────


class TaskUsageViewSet(WorkspaceScopedMixin, viewsets.GenericViewSet):
    """Submit and view per-task usage records."""

    lookup_url_kwarg = "usage_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    serializer_class = TaskUsageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[TaskUsage]:
        return TaskUsage.objects.filter(
            task__agent__workspace_id=self.get_workspace_id()
        )

    @action(detail=False, methods=["post"])
    def submit(self, request):
        task_id = request.data.get("task_id")
        provider = request.data.get("provider")
        model = request.data.get("model")
        if not task_id or not provider or not model:
            raise ValidationError(
                {"detail": "task_id, provider, and model are required."}
            )
        workspace_id = self.get_workspace_id()
        task = Task.objects.filter(id=task_id, agent__workspace_id=workspace_id).first()
        if task is None:
            raise ValidationError({"task_id": "Task must belong to the workspace."})
        usage, _ = TaskUsage.objects.update_or_create(
            task_id=task_id,
            provider=provider,
            model=model,
            defaults={
                "input_tokens": request.data.get("input_tokens", 0),
                "output_tokens": request.data.get("output_tokens", 0),
                "cache_read_tokens": request.data.get("cache_read_tokens", 0),
                "cache_write_tokens": request.data.get("cache_write_tokens", 0),
                "cost": request.data.get("cost", 0.0),
            },
        )
        return Response(TaskUsageSerializer(usage).data, status=status.HTTP_201_CREATED)


class TaskUsageDailyViewSet(WorkspaceScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only view of daily usage rollups."""

    lookup_url_kwarg = "daily_id"
    lookup_value_regex = "[0-9a-f-]{36}"
    from .serializers import TaskUsageDailySerializer

    serializer_class = TaskUsageDailySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[TaskUsageDaily]:
        return TaskUsageDaily.objects.filter(workspace_id=self.get_workspace_id())
