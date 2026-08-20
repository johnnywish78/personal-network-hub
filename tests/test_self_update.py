"""Tests for JPNH self-update (apply-on-restart) and the adoption/status
extensions. No network calls — everything is local or mocked."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from backend.updates.self_update import (apply_staged_source, clear_pending_apply,
                                         pending_apply_info, request_apply,
                                         runtime_mode)
from backend.updates.health import HealthCheckManager
from backend.updates.history import UpdateHistory
from backend.updates.manager import UpdateManager
from backend.updates.manifest import ProjectManifest
from backend.updates.registry import ProjectRegistry
from backend.updates.sources import UpdateSource
from backend.updates.state import UpdateState

from .test_updates import make_manager, make_project


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("JPNH_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("JPNH_DATA_DIR", str(tmp_path / "data"))
    from backend.storage.paths import ensure_data_dir
    ensure_data_dir()
    from backend.services.state import AppState
    from backend.api.v1 import deps
    fresh = AppState()
    monkeypatch.setattr(deps, "app_state", fresh)
    with TestClient(__import__("backend.main", fromlist=["app"]).app) as c:
        yield c


# ---------------------------------------------------------------------------
# runtime mode
# ---------------------------------------------------------------------------

def test_runtime_mode_detection(monkeypatch):
    assert runtime_mode() == "source"  # pytest runs from source
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setenv("APPIMAGE", "/home/u/JPNH.AppImage")
    assert runtime_mode() == "appimage"


# ---------------------------------------------------------------------------
# pending-apply marker
# ---------------------------------------------------------------------------

def test_pending_apply_round_trip(tmp_path):
    assert pending_apply_info() is None
    payload = request_apply("jpnh-core", "/tmp/staged", "0.2.0", mode="source")
    assert payload["project_id"] == "jpnh-core"
    info = pending_apply_info()
    assert info["staged_path"] == "/tmp/staged"
    assert info["expected_version"] == "0.2.0"
    clear_pending_apply()
    assert pending_apply_info() is None


# ---------------------------------------------------------------------------
# apply_staged_source
# ---------------------------------------------------------------------------

def _core_project(root):
    (root / "VERSION").write_text("0.1.0")
    (root / "backend").mkdir()
    (root / "backend" / "main.py").write_text("print('old')")
    return ProjectManifest.from_dict({
        "id": "jpnh-core", "name": "JPNH Core", "source_type": "github",
        "repository": "owner/jpnh", "install_path": ".",
        "staging_only": True, "release_only": True,
        "version_detection": "version_file", "current_version_file": "VERSION",
        "required_files": ["VERSION", "backend/main.py"],
        "health_checks": ["required-files", "version-consistency"],
    })


def _staged_tree(tmp_path, version="0.2.0", missing=None):
    # staged trees always live under the update cache (as the manager places them)
    staged = tmp_path / "data" / "update-cache" / "jpnh-core-0.2.0"
    staged.mkdir(parents=True)
    (staged / "VERSION").write_text(version)
    (staged / "backend").mkdir()
    (staged / "backend" / "main.py").write_text("print('new')")
    if missing:
        (staged / missing).unlink()
    return staged


def test_apply_staged_source_swaps_tree_with_backup(tmp_path):
    root = tmp_path / "root"
    root.mkdir(parents=True)
    project = _core_project(root)
    staged = _staged_tree(tmp_path)
    manager = UpdateManager(root=root)
    manager.registry.register(project)

    marker = request_apply("jpnh-core", str(staged), "0.2.0", mode="source")
    result = apply_staged_source(manager, marker)

    assert result["ok"] is True
    assert result["new_version"] == "0.2.0"
    assert (root / "VERSION").read_text() == "0.2.0"  # applied
    # the previous tree is preserved for rollback
    rollback = Path(result["backup"])
    assert (rollback / "VERSION").read_text() == "0.1.0"
    # marker is cleared
    assert pending_apply_info() is None
    # history + state record the apply
    hist = manager.history.list()
    assert hist[0]["result"] == "applied-on-restart"
    assert hist[0]["build_result"] is not None
    state = manager.state.get("jpnh-core")
    assert state["staged_ref"] is None
    assert state["installed_version"] == "0.2.0"


def test_apply_staged_source_rejects_missing_required_files(tmp_path):
    root = tmp_path / "root"
    root.mkdir(parents=True)
    project = _core_project(root)
    staged = _staged_tree(tmp_path, missing="backend/main.py")
    manager = UpdateManager(root=root)
    manager.registry.register(project)

    marker = request_apply("jpnh-core", str(staged), "0.2.0", mode="source")
    result = apply_staged_source(manager, marker)
    assert result["ok"] is False
    assert "required file" in result["error"]
    assert (root / "VERSION").read_text() == "0.1.0"  # untouched


def test_apply_staged_source_rolls_back_on_health_failure(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir(parents=True)
    project = _core_project(root)
    staged = _staged_tree(tmp_path)
    manager = UpdateManager(root=root)
    manager.registry.register(project)

    class FailingHealth(HealthCheckManager):
        def run(self, *a, **kw):
            return {"ok": False, "checks": [{"name": "required-files", "ok": False, "detail": "boom"}]}
    manager.health = FailingHealth(root=root)

    marker = request_apply("jpnh-core", str(staged), "0.2.0", mode="source")
    result = apply_staged_source(manager, marker)
    assert result["ok"] is False
    assert "health check failed" in result["error"]
    assert (root / "VERSION").read_text() == "0.1.0"  # restored
    assert pending_apply_info() is not None  # marker stays (retry next launch)


# ---------------------------------------------------------------------------
# status entry extensions
# ---------------------------------------------------------------------------

def test_status_entry_includes_health_build_backup_fields(tmp_path):
    # install is adoptable -> status_entry auto-adopts it on scan
    root, manifest = make_project(tmp_path)
    manager = make_manager(tmp_path, manifest, source=None)
    entry = manager.status_entry(manifest)
    assert "health" in entry and entry["health"]["ok"] is True
    assert entry["build"] == {"required": False, "last": None, "detail": None}
    assert entry["backup_available"] == 0
    assert entry["rollback_available"] == 0
    assert entry["adopted"] is True  # adopted on scan (requirement: auto-adoption)


def test_status_entry_reports_adoption(tmp_path):
    root, manifest = make_project(tmp_path)
    manager = make_manager(tmp_path, manifest, source=None)
    assert manager._adopt_if_unmanaged(manifest) is True
    entry = manager.status_entry(manifest)
    assert entry["adopted"] is True
    assert entry["current"]["tracked"] is True


# ---------------------------------------------------------------------------
# rollback rebuilds the component + history detail
# ---------------------------------------------------------------------------

def test_rollback_rebuilds_built_component(tmp_path, monkeypatch):
    root, manifest = make_project(tmp_path, extra={"build_command": "true"})
    built = []
    manager = make_manager(tmp_path, manifest, source=None)
    manager._build = lambda p: built.append(True) or {"ran": True, "failed": False, "detail": "built"}

    # create a real backup via update then roll back
    from backend.updates.sources import UpdateSource

    class FakeSource(UpdateSource):
        def check_available(self, manifest):
            return {"ref": "abc", "ref_type": "commit", "version": "2.0.0",
                    "release_tag": None, "published_at": None, "url": "x",
                    "development": False}
        def download(self, manifest, ref):
            stage = Path(tmp_path) / "stage2"
            stage.mkdir(exist_ok=True)
            (stage / "VERSION").write_text("2.0.0")
            return stage
    manager.source_for = lambda m: FakeSource()
    manager.update("demo", confirm=True)
    backup_id = manager.history.list()[0]["backup_id"]

    built.clear()
    result = manager.rollback(backup_id)
    assert result["ok"] is True
    assert built, "rollback must rebuild the built component"
    hist = manager.history.list()
    assert hist[0]["build_result"] is not None
    assert hist[0]["health_result"]["ok"] is True


def test_history_includes_build_and_health_results(tmp_path):
    root, manifest = make_project(tmp_path)
    manager = make_manager(tmp_path, manifest, source=None)

    from backend.updates.sources import UpdateSource

    class FakeSource(UpdateSource):
        def check_available(self, manifest):
            return {"ref": "abc", "ref_type": "commit", "version": "2.0.0",
                    "release_tag": None, "published_at": None, "url": "x",
                    "development": False}
        def download(self, manifest, ref):
            stage = Path(tmp_path) / "stage3"
            stage.mkdir(exist_ok=True)
            (stage / "VERSION").write_text("2.0.0")
            return stage
    manager.source_for = lambda m: FakeSource()
    result = manager.update("demo", confirm=True)
    assert result["ok"] is True
    hist = manager.history.list()
    # history entries record build + health results for every outcome
    assert "build_result" in hist[0] and "health_result" in hist[0]
    assert hist[0]["build_result"] is None  # no build strategy for demo
    assert hist[0]["health_result"]["ok"] is True


# ---------------------------------------------------------------------------
# network-checker bundle health check verifies executability
# ---------------------------------------------------------------------------

def test_network_checker_bundle_health_checks_executable(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "third_party" / "network-checker").mkdir(parents=True)
    manifest = ProjectManifest.from_dict({
        "id": "network-checker", "name": "Network Checker", "source_type": "github",
        "repository": "mirarr-app/network-checker", "install_path": "third_party/network-checker",
        "version_detection": "file", "current_version_file": "pubspec.yaml",
        "required_files": ["pubspec.yaml", "lib/main.dart"],
        "health_checks": ["required-files", "network-checker-bundle"],
    })
    (root / "third_party" / "network-checker" / "pubspec.yaml").write_text("version: 1.5.0")
    (root / "third_party" / "network-checker" / "lib").mkdir()
    (root / "third_party" / "network-checker" / "lib" / "main.dart").write_text("void main() {}")

    exe = root / "third_party" / "network-checker" / "build" / "linux" / "x64" / "release" / "bundle" / "rdnbenet"
    exe.parent.mkdir(parents=True)
    exe.write_text("binary")
    exe.chmod(0o755)

    h = HealthCheckManager(root=root)
    import backend.updates.health as health_mod
    monkeypatch.setattr(health_mod, "bundle_detected", lambda: True)
    monkeypatch.setattr(health_mod, "bundle_path", lambda: exe)
    ok, detail = h._run_one(manifest, "network-checker-bundle", backend_alive=True)
    assert ok is True
    assert "executable" in detail

    exe.chmod(0o644)  # no execute permission
    ok, detail = h._run_one(manifest, "network-checker-bundle", backend_alive=True)
    assert ok is False
    assert "not executable" in detail

    monkeypatch.setattr(health_mod, "bundle_detected", lambda: False)
    ok, detail = h._run_one(manifest, "network-checker-bundle", backend_alive=True)
    assert ok is False
    assert "not found" in detail


# ---------------------------------------------------------------------------
# API: restart-apply + runtime + overview
# ---------------------------------------------------------------------------

def test_api_overview_includes_runtime_and_pending(api_client):
    r = api_client.get("/updates")
    assert r.status_code == 200
    body = r.json()
    assert body["runtime"] in ("source", "appimage", "deb", "bundled")
    assert body["pending_apply"] is None


def test_api_restart_apply_writes_marker_in_source_mode(api_client, monkeypatch, tmp_path):
    from backend.api.v1 import deps
    manager = deps.app_state.updates
    import backend.api.v1.updates as api_updates

    # stage a fake jpnh-core update inside the update cache
    from backend.storage.paths import update_cache_dir
    staged = update_cache_dir() / "jpnh-core-0.2.0"
    staged.mkdir(parents=True)
    (staged / "VERSION").write_text("0.2.0")
    (staged / "backend").mkdir()
    (staged / "backend" / "main.py").write_text("print('new')")

    manager.state.set("jpnh-core", staged_ref="v0.2.0", staged_version="0.2.0",
                      staged_path=str(staged))
    monkeypatch.setattr(api_updates, "runtime_mode", lambda: "source")
    from backend.storage.paths import pending_apply_path
    pending_apply_path().unlink(missing_ok=True)

    r = api_client.post("/updates/jpnh-core/restart-apply")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    from backend.updates.self_update import pending_apply_info
    info = pending_apply_info()
    assert info["project_id"] == "jpnh-core"
    assert info["staged_path"] == str(staged)
    # cleanup
    pending_apply_path().unlink(missing_ok=True)


def test_api_restart_apply_refuses_packaged_mode(api_client, monkeypatch, tmp_path):
    from backend.api.v1 import deps
    manager = deps.app_state.updates
    import backend.api.v1.updates as api_updates
    from backend.storage.paths import update_cache_dir
    monkeypatch.setattr(api_updates, "runtime_mode", lambda: "appimage")
    staged = update_cache_dir() / "jpnh-core-0.2.0"
    staged.mkdir(parents=True)
    (staged / "VERSION").write_text("0.2.0")
    (staged / "backend").mkdir()
    (staged / "backend" / "main.py").write_text("print('new')")
    manager.state.set("jpnh-core", staged_ref="v0.2.0", staged_version="0.2.0",
                      staged_path=str(staged))
    r = api_client.post("/updates/jpnh-core/restart-apply")
    assert r.status_code == 400
    assert "packaged build" in r.json()["detail"]


def test_api_restart_apply_refuses_without_staged(api_client, monkeypatch):
    from backend.api.v1 import deps
    manager = deps.app_state.updates
    import backend.api.v1.updates as api_updates
    monkeypatch.setattr(api_updates, "runtime_mode", lambda: "source")
    manager.state.set("jpnh-core", staged_ref=None, staged_version=None, staged_path=None)
    r = api_client.post("/updates/jpnh-core/restart-apply")
    assert r.status_code == 400
    assert "no staged update" in r.json()["detail"]


def test_api_restart_apply_refuses_staged_outside_cache(api_client, monkeypatch, tmp_path):
    from backend.api.v1 import deps
    manager = deps.app_state.updates
    import backend.api.v1.updates as api_updates
    monkeypatch.setattr(api_updates, "runtime_mode", lambda: "source")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "VERSION").write_text("0.2.0")
    manager.state.set("jpnh-core", staged_ref="v0.2.0", staged_version="0.2.0",
                      staged_path=str(outside))
    r = api_client.post("/updates/jpnh-core/restart-apply")
    assert r.status_code == 400
    assert "outside the update cache" in r.json()["detail"]


# ---------------------------------------------------------------------------
# CLI: apply_pending
# ---------------------------------------------------------------------------

def test_apply_pending_cli_no_marker(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("JPNH_DATA_DIR", str(tmp_path / "data"))
    from backend.updates.apply_pending import main
    assert main([]) == 0
    assert "no pending self-update" in capsys.readouterr().out


def test_apply_pending_cli_applies_and_clears(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("JPNH_DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "root"
    root.mkdir(parents=True)
    project = _core_project(root)
    staged = _staged_tree(tmp_path)
    manager = UpdateManager(root=root)
    manager.registry.register(project)

    marker = request_apply("jpnh-core", str(staged), "0.2.0", mode="source")
    assert pending_apply_info() is not None

    # the CLI resolves UpdateManager at module level; inject the fixture manager
    from backend.updates.apply_pending import main
    from backend.updates import apply_pending as ap_mod
    ap_mod.UpdateManager = lambda **kw: manager

    assert main([]) == 0
    assert "self-update applied" in capsys.readouterr().out
    assert (root / "VERSION").read_text() == "0.2.0"
    assert pending_apply_info() is None


# ---------------------------------------------------------------------------
# requirement-specific guarantees
# ---------------------------------------------------------------------------

def test_adoption_preserves_local_change_detection(tmp_path):
    """Automatic adoption must baseline the existing tree (no download) and
    keep detecting later local modifications against that baseline."""
    root, manifest = make_project(tmp_path)
    manager = make_manager(tmp_path, manifest, source=None)
    assert manager._adopt_if_unmanaged(manifest) is True
    assert manager.local_changes(manifest)["detected"] is False

    # a local modification after adoption is still detected
    (root / "components" / "demo" / "VERSION").write_text("1.0.0-modified")
    changed = manager.local_changes(manifest)
    assert changed["detected"] is True
    assert changed["tracked"] is True


def test_network_checker_plan_requires_build(tmp_path):
    root = tmp_path / "root"
    (root / "third_party" / "network-checker").mkdir(parents=True)
    (root / "third_party" / "network-checker" / "pubspec.yaml").write_text("version: 1.5.0")
    (root / "third_party" / "network-checker" / "lib").mkdir()
    (root / "third_party" / "network-checker" / "lib" / "main.dart").write_text("void main() {}")
    manifest = ProjectManifest.from_dict({
        "id": "network-checker", "name": "Network Checker", "source_type": "github",
        "repository": "mirarr-app/network-checker", "install_path": "third_party/network-checker",
        "version_detection": "file", "current_version_file": "pubspec.yaml",
        "required_files": ["pubspec.yaml", "lib/main.dart"],
        "health_checks": ["required-files", "network-checker-bundle"],
        "build_strategy": "network-checker",
    })
    manager = UpdateManager(root=root)
    manager.registry.register(manifest)

    from backend.updates.sources import UpdateSource

    class FakeSource(UpdateSource):
        def check_available(self, manifest):
            return {"ref": "v1.6.0", "ref_type": "tag", "version": "1.6.0",
                    "release_tag": "v1.6.0", "published_at": "2026-01-01T00:00:00Z",
                    "url": "https://github.com/mirarr-app/network-checker",
                    "development": False}
        def download(self, manifest, ref):
            stage = Path(tmp_path) / "stage-nc"
            stage.mkdir(exist_ok=True)
            (stage / "pubspec.yaml").write_text("version: 1.6.0")
            return stage
    manager.source_for = lambda m: FakeSource()

    plan = manager.check("network-checker")
    assert plan["status"] == "update-available"
    assert plan["build_required"] is True
    assert plan["available"]["release_tag"] == "v1.6.0"
    assert plan["available"]["published_at"] is not None
    assert plan["available"]["url"]  # release info exposed (requirement 8)


def test_backup_manifest_records_source_reason_version_and_ref(tmp_path):
    root, manifest = make_project(tmp_path)
    manager = make_manager(tmp_path, manifest, source=None)

    from backend.updates.sources import UpdateSource

    class FakeSource(UpdateSource):
        def check_available(self, manifest):
            return {"ref": "abc123", "ref_type": "commit", "version": "2.0.0",
                    "release_tag": None, "published_at": None, "url": "x",
                    "development": False}
        def download(self, manifest, ref):
            stage = Path(tmp_path) / "stage-b"
            stage.mkdir(exist_ok=True)
            (stage / "VERSION").write_text("2.0.0")
            return stage
    manager.source_for = lambda m: FakeSource()
    manager.update("demo", confirm=True)

    backup_id = manager.history.list()[0]["backup_id"]
    from backend.updates.backup import _read_json
    info = manager.backup.get(backup_id)
    manifest_data = _read_json(Path(info["path"]) / "manifest.json")
    assert manifest_data["backup_id"] == backup_id
    assert manifest_data["project"] == "demo"
    assert manifest_data["source"] == "github"
    assert manifest_data["reason"] == "update"
    metadata = _read_json(Path(info["path"]) / "metadata.json")
    assert metadata["version_info"]["old_version"] == "1.0.0"
    assert metadata["version_info"]["new_ref"] == "abc123"
    assert metadata["version_info"]["new_version"] == "2.0.0"
    assert metadata["project"]["id"] == "demo"


def test_jpnh_core_health_checks(tmp_path):
    root = tmp_path / "root"
    root.mkdir(parents=True)
    (root / "VERSION").write_text("0.1.0")
    (root / "backend").mkdir()
    (root / "backend" / "main.py").write_text("print('ok')")
    manifest = ProjectManifest.from_dict({
        "id": "jpnh-core", "name": "JPNH Core", "source_type": "github",
        "repository": "owner/jpnh", "install_path": ".",
        "staging_only": True, "release_only": True,
        "version_detection": "version_file", "current_version_file": "VERSION",
        "required_files": ["VERSION", "backend/main.py"],
        "health_checks": ["required-files", "version-consistency"],
    })
    h = HealthCheckManager(root=root)
    result = h.run(manifest, backend_alive=True)
    assert result["ok"] is True
    names = {c["name"] for c in result["checks"]}
    assert {"required-files", "version-consistency"} <= names

    # missing required file -> not healthy
    (root / "backend" / "main.py").unlink()
    result = h.run(manifest, backend_alive=True)
    assert result["ok"] is False


def test_history_entry_has_all_fields(tmp_path):
    root, manifest = make_project(tmp_path)
    manager = make_manager(tmp_path, manifest, source=None)

    from backend.updates.sources import UpdateSource

    class FakeSource(UpdateSource):
        def check_available(self, manifest):
            return {"ref": "abc", "ref_type": "commit", "version": "2.0.0",
                    "release_tag": None, "published_at": None, "url": "x",
                    "development": False}
        def download(self, manifest, ref):
            stage = Path(tmp_path) / "stage-h"
            stage.mkdir(exist_ok=True)
            (stage / "VERSION").write_text("2.0.0")
            return stage
    manager.source_for = lambda m: FakeSource()
    manager.update("demo", confirm=True)

    entry = manager.history.list()[0]
    for key in ("id", "timestamp", "project", "old_version", "new_version",
                "result", "error", "backup_id", "rollback_status",
                "build_result", "health_result"):
        assert key in entry, f"history entry missing '{key}'"


def test_update_all_continues_after_component_failure(tmp_path):
    root = tmp_path / "root"
    (root / "components" / "aa").mkdir(parents=True)
    (root / "components" / "aa" / "VERSION").write_text("1.0.0")
    (root / "components" / "bb").mkdir(parents=True)
    (root / "components" / "bb" / "VERSION").write_text("1.0.0")
    m_a = ProjectManifest.from_dict({
        "id": "aa", "name": "A", "source_type": "github", "repository": "o/a",
        "install_path": "components/aa", "version_detection": "version_file",
        "current_version_file": "VERSION", "required_files": ["VERSION"],
        "health_checks": ["required-files"],
    })
    m_b = ProjectManifest.from_dict({
        "id": "bb", "name": "B", "source_type": "github", "repository": "o/b",
        "install_path": "components/bb", "version_detection": "version_file",
        "current_version_file": "VERSION", "required_files": ["VERSION"],
        "health_checks": ["required-files"],
    })
    registry = ProjectRegistry()
    registry.register(m_a)
    registry.register(m_b)
    manager = UpdateManager(root=root, registry=registry)

    from backend.updates.sources import UpdateSource, UpdateSourceError

    class MixedSource(UpdateSource):
        def check_available(self, manifest):
            return {"ref": "x", "ref_type": "commit", "version": "2.0.0",
                    "release_tag": None, "published_at": None, "url": "x",
                    "development": False}
        def download(self, manifest, ref):
            if manifest.id == "bb":
                raise UpdateSourceError("download failed: offline")
            stage = Path(tmp_path) / "stage-u"
            stage.mkdir(exist_ok=True)
            (stage / "VERSION").write_text("2.0.0")
            return stage
    manager.source_for = lambda m: MixedSource()

    result = manager.update_all(confirm=True)
    summary = {s["project_id"]: s for s in result["summary"]}
    assert summary["aa"]["status"] == "success"
    assert summary["bb"]["status"] == "failed"
    assert "download failed" in summary["bb"]["error"]
    # per-component rollback was available for the failed one
    assert summary["bb"]["backup_id"]


def test_pending_apply_marker_contains_no_secrets(tmp_path):
    from backend.updates.self_update import request_apply, pending_apply_info
    payload = request_apply("jpnh-core", "/cache/jpnh-core-x", "0.2.0", mode="source")
    text = json.dumps(payload)
    assert "secret" not in text.lower()
    assert "password" not in text.lower()
    assert "token" not in text.lower()
    assert "http://user:" not in text


def test_bpb_not_hardcoded_but_registrable_via_generic_registry(tmp_path):
    """BPB must not be a hard-coded update component; the generic registry
    accepts it as a user manifest the same as any other project."""
    from backend.updates.registry import BUILTIN_PROJECTS
    ids = {p["id"] for p in BUILTIN_PROJECTS}
    assert "bpb" not in ids and "bpb-worker-panel" not in ids

    registry = ProjectRegistry(user_dir=Path(tmp_path) / "projects")
    bpb = ProjectManifest.from_dict({
        "id": "bpb-worker-panel", "name": "BPB Worker Panel", "source_type": "github",
        "repository": "bia-pain-bache/BPB-Worker-Panel", "install_path": "third_party/bpb",
        "version_detection": "file", "current_version_file": "VERSION",
        "required_files": ["VERSION"],
    })
    registry.register(bpb)
    assert registry.get("bpb-worker-panel") is not None


def test_apply_pending_cli_refuses_staged_outside_cache(tmp_path, capsys, monkeypatch):
    """The CLI must refuse a marker whose staged path is outside the update
    cache — this is the guard that prevents an accidental self-swap."""
    monkeypatch.setenv("JPNH_DATA_DIR", str(tmp_path / "data"))
    root = tmp_path / "root"
    root.mkdir(parents=True)
    project = _core_project(root)
    manager = UpdateManager(root=root)
    manager.registry.register(project)

    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "VERSION").write_text("0.2.0")
    marker = request_apply("jpnh-core", str(outside), "0.2.0", mode="source")

    result = apply_staged_source(manager, marker)
    assert result["ok"] is False
    assert "outside the update cache" in result["error"]
    assert (root / "VERSION").read_text() == "0.1.0"
    assert pending_apply_info() is not None  # marker untouched