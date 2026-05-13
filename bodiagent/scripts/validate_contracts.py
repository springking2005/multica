"""Contract validation — validates OpenAPI schema, schema.sql ↔ Django models, and WS events."""

import os
import re
import sys
from pathlib import Path

import django
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = ROOT / ".." / ".omc" / "contracts"
DJANGO_PROJECT = ROOT


def load_openapi():
    path = CONTRACTS_DIR / "openapi.yaml"
    if not path.exists():
        print(f"ERROR: openapi.yaml not found at {path}")
        return None
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"ERROR: Failed to parse openapi.yaml: {e}")
        return None


def validate_openapi_schema_refs(spec):
    """Verify all $ref targets in components.schemas exist."""
    errors = []
    schemas = set(spec.get("components", {}).get("schemas", {}).keys())

    def _check_refs(obj, path="<root>"):
        if isinstance(obj, dict):
            if "$ref" in obj:
                ref = obj["$ref"]
                if ref.startswith("#/components/schemas/"):
                    name = ref[len("#/components/schemas/"):]
                    if name not in schemas:
                        errors.append(f"Unresolved $ref '{ref}' at {path}")
            for k, v in obj.items():
                _check_refs(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _check_refs(item, f"{path}[{i}]")

    _check_refs(spec)
    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return False
    print(f"OK: All {len(schemas)} schema references resolved ({len(schemas)} schemas in components).")
    return True


def validate_sql_vs_django_models():
    """Compare schema.sql CREATE TABLE statements against Django model db_table names."""
    sql_path = CONTRACTS_DIR / "schema.sql"
    if not sql_path.exists():
        print(f"ERROR: schema.sql not found at {sql_path}")
        return False

    with open(sql_path) as f:
        sql_content = f.read()

    sql_tables = set(re.findall(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?\s*"?(\w+)"?', sql_content, re.IGNORECASE))

    # Set up Django to discover models
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bodiagent.settings_dev")
    sys.path.insert(0, str(DJANGO_PROJECT))
    try:
        django.setup()
    except Exception as e:
        print(f"ERROR: Failed to setup Django: {e}")
        return False

    from django.apps import apps  # noqa: E402

    django_tables: set[str] = set()
    for app_config in apps.get_app_configs():
        # Only include BodiAgent apps
        if app_config.name in ("accounts", "issues", "agents", "inbox", "chat", "projects", "autopilots"):
            for model in app_config.get_models():
                table_name = model._meta.db_table
                django_tables.add(table_name)

    # Phase 0 tables known to exist in schema.sql but not yet modelled in Django
    known_divergences = {"feedback"}

    errors = []
    for table in sorted(sql_tables):
        if table not in django_tables and table not in known_divergences:
            errors.append(f"Table '{table}' exists in schema.sql but has NO Django model")
    for table in sorted(django_tables):
        if table not in sql_tables:
            errors.append(f"Django model db_table '{table}' has NO matching table in schema.sql")

    if known_divergences & sql_tables:
        print(f"NOTE: Known Phase 0 divergences (not yet modelled): {sorted(known_divergences & sql_tables)}")

    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return False
    print(f"OK: schema.sql tables ({len(sql_tables)}) match Django models ({len(django_tables)}).")
    return True


def validate_ws_events_in_openapi(spec):
    """Verify that WS event domains from ws-events.md are referenced in openapi.yaml WS paths."""
    ws_events_path = CONTRACTS_DIR / "ws-events.md"
    if not ws_events_path.exists():
        print(f"ERROR: ws-events.md not found at {ws_events_path}")
        return False

    with open(ws_events_path) as f:
        ws_content = f.read()

    # Extract event type prefixes from the event catalog table (e.g. "issue:" from "issue:created")
    # Match lines like | `issue:created` | workspace | ...
    event_prefixes: set[str] = set()
    for match in re.finditer(r'`([a-z_]+):[a-z_]+`', ws_content):
        prefix = match.group(1)
        # Skip daemon WS frame types which are inbound-only
        if prefix not in ("subscribe", "unsubscribe", "ping", "auth"):
            event_prefixes.add(prefix)

    # Check that these domains are represented in the openapi spec
    # Strategy: check tags used across paths AND the WS path descriptions
    all_tags: set[str] = set()
    ws_descriptions: list[str] = []

    paths = spec.get("paths", {})
    for path_key, path_item in paths.items():
        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if op is None:
                continue
            all_tags.update(op.get("tags", []))
            # Collect WS descriptions
            if "websocket" in op.get("tags", []) or "ws" in str(path_key).lower():
                desc = op.get("description", "") + " " + op.get("summary", "")
                ws_descriptions.append(desc.lower())

    # Also check path keys for WS routes
    ws_paths = {k for k in paths if "ws" in k.lower()}

    errors = []
    ws_combined_text = " ".join(ws_descriptions) + " " + " ".join(all_tags)

    # Map ws-events.md domain prefixes to OpenAPI tags (singular).
    # Nested concepts (reactions, activity, subscribers, etc.) map to parent resource tags.
    domain_tag_map: dict[str, list[str]] = {
        "issue": ["issue"],
        "comment": ["comment"],
        "task": ["task"],
        "agent": ["agent"],
        "inbox": ["inbox"],
        "workspace": ["workspace"],
        "member": ["member"],
        "subscriber": ["issue"],          # subscriber:added is part of issue domain
        "activity": ["issue"],            # activity:created is part of issue domain
        "skill": ["skill"],
        "chat": ["chat"],
        "project": ["project"],
        "label": ["label"],
        "pin": ["pin"],
        "invitation": ["member"],         # invitation events live under member domain
        "autopilot": ["autopilot"],
        "daemon": ["daemon"],
        "reaction": ["comment", "issue"],  # reactions live on comments and issues
        "project_resource": ["project"],    # nested under projects
        "issue_reaction": ["issue"],        # nested under issues
        "issue_labels": ["issue", "label"], # nested under issues and labels
    }

    for prefix in sorted(event_prefixes):
        expected_tags = domain_tag_map.get(prefix, [prefix])
        found = (
            any(t in all_tags for t in expected_tags)
            or any(t in ws_combined_text for t in expected_tags)
            or prefix in ws_combined_text
        )
        if not found:
            errors.append(
                f"WS event domain '{prefix}' not found in openapi.yaml "
                f"(expected tags: {expected_tags}, available tags: {sorted(all_tags)})"
            )

    if not ws_paths:
        errors.append("No WebSocket paths (/ws, /api/daemon/ws) found in openapi.yaml")

    if errors:
        for err in errors:
            print(f"ERROR: {err}")
        return False

    print(f"OK: All {len(event_prefixes)} WS event domains referenced in openapi.yaml "
          f"(tags: {sorted(all_tags)}, WS paths: {sorted(ws_paths)}).")
    return True


def main():
    spec = load_openapi()
    if spec is None:
        return 1

    ok = True

    # 1. Validate schema refs
    if not validate_openapi_schema_refs(spec):
        ok = False

    # 2. Validate SQL vs Django models
    if not validate_sql_vs_django_models():
        ok = False

    # 3. Validate WS events
    if not validate_ws_events_in_openapi(spec):
        ok = False

    if ok:
        print("\nContract validation PASSED")
        return 0
    else:
        print("\nContract validation FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
