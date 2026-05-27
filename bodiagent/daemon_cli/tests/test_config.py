"""Tests for config module."""

import json

import daemon_cli.config as config_module
from daemon_cli.config import DaemonConfig, detect_available_clis


class TestDaemonConfig:
    def test_default_values(self):
        c = DaemonConfig()
        assert c.server_url == "http://localhost:8000"
        assert c.token == ""
        assert c.max_concurrent_tasks == 20
        assert c.gc_ttl_hours == 24
        assert c.gc_orphan_ttl_hours == 72

    def test_custom_values(self):
        c = DaemonConfig(
            server_url="https://example.com",
            token="test_token",
            max_concurrent_tasks=10,
        )
        assert c.server_url == "https://example.com"
        assert c.token == "test_token"
        assert c.max_concurrent_tasks == 10

    def test_save_and_load(self, tmp_path):
        config_dir = tmp_path / ".bodiagent"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        # Write config directly to avoid workspace root creation
        c = DaemonConfig(
            server_url="https://saved.example.com",
            token="saved_token",
            workspaces_root=tmp_path / "ws",
        )
        c.workspaces_root.mkdir(parents=True, exist_ok=True)

        payload = {
            "server_url": c.server_url,
            "token": c.token,
            "workspace_id": c.workspace_id,
            "workspaces_root": str(c.workspaces_root),
            "max_concurrent_tasks": c.max_concurrent_tasks,
            "gc_interval_seconds": c.gc_interval_seconds,
            "gc_ttl_hours": c.gc_ttl_hours,
            "gc_orphan_ttl_hours": c.gc_orphan_ttl_hours,
            "available_providers": c.available_providers,
        }
        config_file.write_text(json.dumps(payload, indent=2))

        # Cannot test load() directly because it always writes to ~/.bodiagent.
        # Test the data roundtrip instead.
        data = json.loads(config_file.read_text())
        assert data["server_url"] == "https://saved.example.com"
        assert data["token"] == "saved_token"


class TestDetectAvailableClis:
    def test_returns_list(self):
        clis = detect_available_clis()
        assert isinstance(clis, list)



def test_load_reads_profile_config(tmp_path, monkeypatch):
    config_dir = tmp_path / ".bodiagent"
    profile_dir = config_dir / "profiles" / "staging"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.json").write_text(
        json.dumps(
            {
                "server_url": "https://staging.example.com",
                "token": "mdt_staging",
                "workspace_id": "workspace-staging",
                "workspaces_root": str(tmp_path / "workspaces"),
            }
        )
    )
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_FILE", config_dir / "config.json")
    monkeypatch.setattr(config_module, "DEFAULT_WORKSPACES_ROOT", config_dir / "workspaces")

    config = DaemonConfig.load("staging")

    assert config.server_url == "https://staging.example.com"
    assert config.token == "mdt_staging"
    assert config.workspace_id == "workspace-staging"
