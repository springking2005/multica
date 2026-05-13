"""Serializers for autopilot APIs."""

from __future__ import annotations

from rest_framework import serializers

from .models import Autopilot, AutopilotRun, AutopilotTrigger


class AutopilotTriggerSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutopilotTrigger
        fields = [
            "id",
            "autopilot",
            "kind",
            "enabled",
            "cron_expression",
            "timezone",
            "next_run_at",
            "webhook_token",
            "label",
            "last_fired_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "autopilot",
            "created_at",
            "updated_at",
        ]


class AutopilotRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutopilotRun
        fields = [
            "id",
            "autopilot",
            "trigger",
            "source",
            "status",
            "issue",
            "task",
            "triggered_at",
            "completed_at",
            "failure_reason",
            "trigger_payload",
            "result",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "autopilot",
            "trigger",
            "triggered_at",
            "completed_at",
            "created_at",
        ]


class AutopilotSerializer(serializers.ModelSerializer):
    triggers = AutopilotTriggerSerializer(many=True, read_only=True)

    class Meta:
        model = Autopilot
        fields = [
            "id",
            "workspace",
            "title",
            "description",
            "assignee",
            "status",
            "execution_mode",
            "issue_title_template",
            "created_by_type",
            "created_by_id",
            "last_run_at",
            "triggers",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "workspace",
            "created_at",
            "updated_at",
        ]


class AutopilotCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Autopilot
        fields = [
            "id",
            "title",
            "description",
            "assignee",
            "status",
            "execution_mode",
            "issue_title_template",
            "created_by_type",
            "created_by_id",
            "last_run_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class AutopilotTriggerCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutopilotTrigger
        fields = [
            "id",
            "kind",
            "enabled",
            "cron_expression",
            "timezone",
            "webhook_token",
            "label",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


class AutopilotTriggerUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutopilotTrigger
        fields = [
            "kind",
            "enabled",
            "cron_expression",
            "timezone",
            "webhook_token",
            "label",
        ]


class ManualTriggerSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(
        choices=Autopilot.ExecutionMode.choices,
        default=Autopilot.ExecutionMode.RUN_ONLY,
    )
