# Generated for daemon workspace binding security boundary

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="DaemonWorkspaceBinding",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_daemon_bindings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "daemon",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="workspace_bindings",
                        to="accounts.daemon",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="daemon_bindings",
                        to="accounts.workspace",
                    ),
                ),
            ],
            options={
                "db_table": "daemon_workspace_binding",
                "indexes": [
                    models.Index(fields=["workspace", "revoked_at"], name="idx_daemon_binding_ws"),
                    models.Index(fields=["daemon", "revoked_at"], name="idx_daemon_binding_daemon"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("daemon", "workspace"), name="daemon_workspace_binding_unique"),
                ],
            },
        ),
    ]
