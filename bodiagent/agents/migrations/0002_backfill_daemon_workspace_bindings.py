# Backfill daemon workspace bindings from existing agents.

from django.db import migrations


def forwards(apps, schema_editor):
    Agent = apps.get_model("agents", "Agent")
    binding_model = apps.get_model("accounts", "DaemonWorkspaceBinding")
    pairs = (
        Agent.objects.exclude(daemon_id__isnull=True)
        .values_list("daemon_id", "workspace_id")
        .distinct()
    )
    for daemon_id, workspace_id in pairs:
        binding_model.objects.get_or_create(daemon_id=daemon_id, workspace_id=workspace_id)


def backwards(apps, schema_editor):
    # Keep bindings; they are security state and may have been edited after migration.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_daemon_workspace_binding"),
        ("agents", "0001_initial"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
