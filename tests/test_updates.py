"""Tests for the Update Manager / Project Manager subsystem.

Covers: version comparison, registry, sources, backup/restore, rollback,
dry-run, successful/failed updates, health checks, Update All, proxy env
handling, secrets-in-logs, and malformed manifests. Network calls are
always mocked — no test touches a real remote.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from backend.updates.backup import BackupManager
from backend.updates.health import HealthCheckManager
from backend.updates.history import UpdateHistory
from backend.updates.manager import UpdateManager, UpdateManagerError
from backend.updates.manifest import ProjectManifest
from backend.updates.registry import ProjectRegistry
from backend.updates.sources import (GitHubSource, LocalSource,
                                     UpdateSource, UpdateSourceError,
                                     _build_client, parse_version_from_file,
                                     parse_version_text)
from backend.updates.state import UpdateState
from backend.updates.versions import Version, compare_versions, strip_tag


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setenv("JPNH_DATA_DIR", str(tmp_path / "data"))
    return tmp_path


class FakeSource(UpdateSource):
    """Deterministic source for manager-level tests (no network)."""

    def __init__(self, available=None, staged=None, fail="", version="2.0.0",
                 ref="abc123def456", missing_required=None):
        self.available = available or {
            "ref": ref, "ref_type": "commit", "version": version,
            "release_tag": None, "published_at": None,
            "url": "https://github.com/owner/demo", "development": False}
        self.staged = staged
        self.fail = fail
        self.missing_required = missing_required or []

    def check_available(self, manifest):
        if self.fail == "check":
            raise UpdateSourceError("upstream unreachable")
        return dict(self.available)

    def download(self, manifest, ref):
        if self.fail == "download":
            raise UpdateSourceError("download failed: could not reach host")
        if self.staged is not None:
            return self.staged
        stage = Path(tempfile.mkdtemp())
        for rel in manifest.required_files:
            if rel in self.missing_required:
                continue
            path = stage / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{self.available['version']}\n" if rel == "VERSION" else "new content")
        return stage


def make_project(tmp_path, project_id="demo", install="components/demo",
                 version="1.0.0", build="none", required=("VERSION",),
                 extra=None):
    root = tmp_path / "root"
    install_dir = root / install
    install_dir.mkdir(parents=True, exist_ok=True)
    (install_dir / "VERSION").write_text(version)
    data = {
        "id": project_id,
        "name": "Demo Project",
        "source_type": "github",
        "repository": "owner/demo",
        "branch": "main",
        "install_path": install,
        "update_strategy": "download",
        "build_strategy": build,
        "version_detection": "version_file",
        "current_version_file": "VERSION",
        "required_files": list(required),
        "health_checks": ["required-files"],
    }
    if extra:
        data.update(extra)
    manifest = ProjectManifest.from_dict(data)
    return root, manifest


def make_manager(tmp_path, manifest, source=None, log=None):
    registry = ProjectRegistry()
    registry.register(manifest)
    manager = UpdateManager(
        registry=registry,
        state=UpdateState(),
        history=UpdateHistory(),
        backup=BackupManager(root=tmp_path / "root"),
        health=HealthCheckManager(root=tmp_path / "root"),
        root=tmp_path / "root",
        log=log,
    )
    if source is not None:
        manager.source_for = lambda m: source
    return manager


# ---------------------------------------------------------------------------
# version comparison
# ---------------------------------------------------------------------------

def test_version_sources_are_consistent():
    """VERSION file is the single source of truth; the desktop package and the
    backend must not drift away from it."""
    from backend.version import get_version
    repo_root = Path(__file__).resolve().parents[1]
    version_file = (repo_root / "VERSION").read_text(encoding="utf-8").strip()
    assert get_version() == version_file
    pkg = json.loads((repo_root / "desktop" / "package.json").read_text(encoding="utf-8"))
    assert pkg["version"] == version_file


def test_version_parsing_and_compare():
    assert Version("1.2.3").parts == (1, 2, 3)
    assert Version("v2.0.0").parts == (2, 0, 0)
    assert not Version("") and not Version("abc")
    assert compare_versions("1.2.0", "1.10.0") == -1
    assert compare_versions("1.10.0", "1.2.0") == 1
    assert compare_versions("1.2.0", "1.2.0") == 0
    assert compare_versions(None, "1.2.0") is None
    assert compare_versions("1.2.0", "garbage") is None


def test_strip_tag():
    assert strip_tag("v1.2.3") == "1.2.3"
    assert strip_tag("jpnh-0.1.0") == "0.1.0"


def test_version_compare_ignores_build_metadata():
    # Flutter "+build" metadata must never change the version comparison.
    assert compare_versions("1.6.0", "1.6.0+123") == 0
    assert compare_versions("1.6.0+1", "1.6.0") == 0
    assert compare_versions("1.6.0", "1.6.0+build42") == 0
    assert compare_versions("1.5.0", "1.6.0+1") == -1
    assert compare_versions("v1.6.0", "1.6.0") == 0
    assert compare_versions("v1.6.0", "1.6.0+7") == 0


def test_parse_version_text_variants():
    cases = [
        ("version: 1.5.0", "1.5.0"),
        ("version: 1.6.0", "1.6.0"),
        ("version: 1.6.0+1", "1.6.0"),
        ("version: v1.6.0", "1.6.0"),
        ("version: 1.6.0+abc", "1.6.0"),
        ("version: garbage", None),
        ("version: ", None),
        ("name: x\nversion: 0.9.0\n", "0.9.0"),
        ("", None),
    ]
    for text, expected in cases:
        assert parse_version_text(text, "pubspec.yaml") == expected, text
    # non-yaml file: first line is the version
    assert parse_version_text("0.1.0\n", "VERSION") == "0.1.0"
    assert parse_version_text("garbage\n", "VERSION") is None
    assert parse_version_text("v0.2.0\n", "VERSION") == "0.2.0"


# ---------------------------------------------------------------------------
# project registry / manifests
# ---------------------------------------------------------------------------

def test_registry_builtins():
    registry = ProjectRegistry(user_dir=Path(tempfile.mkdtemp()))
    ids = registry.ids()
    assert "jpnh-core" in ids and "network-checker" in ids
    nc = registry.get("network-checker")
    assert nc.repository == "mirarr-app/network-checker"
    assert nc.install_path == "third_party/network-checker"


def test_registry_user_manifest_loaded(tmp_path):
    projects = tmp_path / "data" / "projects"
    projects.mkdir(parents=True)
    (projects / "future-tool.json").write_text(json.dumps({
        "id": "future-tool", "name": "Future Tool", "source_type": "github",
        "repository": "owner/future-tool", "install_path": "third_party/future-tool",
        "build_strategy": "none", "version_detection": "version_file",
    }))
    registry = ProjectRegistry(user_dir=projects)
    assert "future-tool" in registry.ids()
    assert registry.errors() == []


def test_registry_malformed_user_manifest_skipped(tmp_path):
    projects = tmp_path / "data" / "projects"
    projects.mkdir(parents=True)
    (projects / "bad.json").write_text(json.dumps({
        "id": "bad", "source_type": "evil", "update_strategy": "rm -rf /",
        "install_path": "../../escape",
    }))
    (projects / "good.json").write_text(json.dumps({
        "id": "good", "name": "Good", "source_type": "local",
        "install_path": "third_party/good",
    }))
    registry = ProjectRegistry(user_dir=projects)
    ids = registry.ids()
    assert "good" in ids and "bad" not in ids
    assert any("bad" in e for e in registry.errors())


def test_registry_user_manifest_cannot_override_builtin(tmp_path):
    """A per-user manifest must never replace a built-in project; otherwise a
    stray file could redirect the vendored Network Checker or JPNH core to an
    arbitrary repository."""
    projects = tmp_path / "data" / "projects"
    projects.mkdir(parents=True)
    (projects / "network-checker.json").write_text(json.dumps({
        "id": "network-checker", "name": "EVIL", "source_type": "github",
        "repository": "attacker/repo", "install_path": "third_party/evil",
        "version_detection": "version_file", "current_version_file": "VERSION",
    }))
    (projects / "mine.json").write_text(json.dumps({
        "id": "mine", "name": "Mine", "source_type": "local",
        "install_path": "third_party/mine",
    }))
    registry = ProjectRegistry(user_dir=projects)
    nc = registry.get("network-checker")
    assert nc.repository == "mirarr-app/network-checker"  # built-in wins
    assert "mine" in registry.ids()
    assert any("cannot override built-in" in e for e in registry.errors())


def test_manifest_rejects_unsafe_values():
    with pytest.raises(ValueError):
        ProjectManifest.from_dict({"id": "ok", "install_path": "../escape"})
    with pytest.raises(ValueError):
        m = ProjectManifest.from_dict({"id": "ok", "source_type": "ftp"})
        m.validate()
    with pytest.raises(ValueError):
        ProjectManifest.from_dict({"id": "ok", "repository": "not-a-repo"})
    with pytest.raises(ValueError):
        ProjectManifest.from_dict({"id": "ok", "build_command": "a; rm -rf /"})


# ---------------------------------------------------------------------------
# network checker current detection
# ---------------------------------------------------------------------------

def test_network_checker_current_version_detected(tmp_path):
    root = tmp_path / "root"
    install = root / "third_party" / "network-checker"
    install.mkdir(parents=True)
    (install / "pubspec.yaml").write_text("name: rdnbenet\nversion: 1.5.0\n")
    (install / "lib").mkdir()
    (install / "lib" / "main.dart").write_text("void main() {}")
    manifest = ProjectManifest.from_dict({
        "id": "network-checker", "name": "Network Checker", "source_type": "github",
        "repository": "mirarr-app/network-checker",
        "install_path": "third_party/network-checker",
        "version_detection": "file", "current_version_file": "pubspec.yaml",
    })
    manager = UpdateManager(root=root)
    cur = manager.current_version(manifest)
    assert cur["version"] == "1.5.0"
    assert cur["tracked"] is False
    assert cur["installed"] is True


# ---------------------------------------------------------------------------
# local modification detection
# ---------------------------------------------------------------------------

def test_local_changes_detected(tmp_path):
    root, manifest = make_project(tmp_path)
    manager = UpdateManager(root=root)
    install_dir = root / "components" / "demo"
    manager._write_metadata(manifest, {
        "ref": "old", "ref_type": "commit", "version": "1.0.0",
        "installed_fingerprint": _fingerprint(install_dir, manifest),
        "installed_hashes": _hashes(install_dir, manifest),
    })
    # pristine -> no changes
    assert manager.local_changes(manifest)["detected"] is False
    # modify a tracked file -> detected
    (install_dir / "VERSION").write_text("1.0.0-LOCAL")
    local = manager.local_changes(manifest)
    assert local["detected"] is True
    assert local["files"]
    # untracked install -> conservative
    other, other_manifest = make_project(tmp_path, project_id="untracked",
                                         install="components/untracked")
    assert manager.local_changes(other_manifest)["detected"] is None


# ---------------------------------------------------------------------------
# backup / restore
# ---------------------------------------------------------------------------

def test_backup_create_and_restore(tmp_path):
    root, manifest = make_project(tmp_path)
    install_dir = root / "components" / "demo"
    backup = BackupManager(root=root)
    backup_id = backup.create(manifest, version_info={"old_version": "1.0.0"},
                              credential_keys=["github_token"])
    info = backup.get(backup_id)
    assert info and info["project"] == "demo"
    assert (Path(info["path"]) / "manifest.json").exists()
    assert (Path(info["path"]) / "metadata.json").exists()
    assert json.loads((Path(info["path"]) / "metadata.json").read_text())["credential_keys"] == ["github_token"]

    (install_dir / "VERSION").write_text("9.9.9")
    restored = backup.restore(backup_id, manifest)
    assert restored["project_restored"] is True
    assert (install_dir / "VERSION").read_text() == "1.0.0"

    assert any(b["backup_id"] == backup_id for b in backup.list("demo"))
    assert backup.delete(backup_id) is True
    assert backup.get(backup_id) is None


def test_backup_rejects_invalid_id():
    backup = BackupManager(root=Path(tempfile.mkdtemp()))
    with pytest.raises(ValueError):
        backup.resolve("../../escape")


def test_backup_create_with_existing_state_files(tmp_path, isolated_data):
    """State snapshotting must not crash when real state files exist: the
    backup's state/ directory has to be created before copying them."""
    root, manifest = make_project(tmp_path)
    from backend.storage.paths import settings_path, services_path
    settings_path().parent.mkdir(parents=True, exist_ok=True)
    settings_path().write_text('{"theme": "dark"}')
    services_path().write_text('{"services": []}')
    backup = BackupManager(root=root)
    backup_id = backup.create(manifest, version_info={"old_version": "1.0.0"})
    info = backup.get(backup_id)
    assert info is not None
    state_dir = Path(info["path"]) / "state"
    assert (state_dir / "settings.json").exists()
    assert (state_dir / "settings.json").read_text() == '{"theme": "dark"}'
    # secret values never appear in backup metadata
    meta = json.loads((Path(info["path"]) / "metadata.json").read_text())
    assert "secret" not in json.dumps(meta).lower()


def test_backup_restore_staging_only_never_touches_checkout(tmp_path, isolated_data):
    """Rolling back a staging-only project (JPNH core) must restore user state
    but NEVER replace the running checkout in place."""
    root = tmp_path / "root"
    root.mkdir(parents=True)
    (root / "VERSION").write_text("0.1.0")
    (root / "backend").mkdir()
    (root / "backend" / "main.py").write_text("print('ok')")
    manifest = ProjectManifest.from_dict({
        "id": "jpnh-core", "name": "JPNH Core", "source_type": "github",
        "repository": "owner/jpnh", "install_path": ".", "staging_only": True,
    })
    from backend.storage.paths import settings_path
    settings_path().parent.mkdir(parents=True, exist_ok=True)
    settings_path().write_text('{"theme": "dark"}')
    backup = BackupManager(root=root)
    backup_id = backup.create(manifest, version_info={"old_version": "0.1.0"})
    # simulate the checkout changing while the staged update sits in state
    (root / "VERSION").write_text("CHANGED")
    restored = backup.restore(backup_id, manifest)
    assert restored["project_restored"] is False
    assert (root / "VERSION").read_text() == "CHANGED"  # checkout untouched
    # state files still restored
    assert "settings" in restored["state_restored"]


def test_backup_timestamps_have_microseconds(tmp_path):
    from backend.updates.backup import _timestamp_safe
    assert len(_timestamp_safe()) >= 22  # ...%fZ adds >6 digits


# ---------------------------------------------------------------------------
# check / dry-run
# ---------------------------------------------------------------------------

def test_dry_run_never_modifies(tmp_path):
    root, manifest = make_project(tmp_path)
    source = FakeSource()
    manager = make_manager(tmp_path, manifest, source=source)
    before = sorted(p.name for p in (root / "components" / "demo").iterdir())

    plan = manager.check("demo")
    assert plan["would_update"] is True
    assert plan["requires_confirmation"] is True   # untracked install
    assert plan["available"]["version"] == "2.0.0"
    after = sorted(p.name for p in (root / "components" / "demo").iterdir())
    assert before == after
    assert not list((tmp_path / "data" / "backups").iterdir()) if (tmp_path / "data" / "backups").exists() else True


def test_check_network_error_is_graceful(tmp_path):
    root, manifest = make_project(tmp_path)
    manager = make_manager(tmp_path, manifest, source=FakeSource(fail="check"))
    plan = manager.check("demo")
    assert plan["status"] == "error"
    assert "unreachable" in plan["error"]
    assert manager.dry_run("demo")["plan"]["status"] == "error"


def test_dry_run_all(tmp_path):
    root, manifest = make_project(tmp_path)
    manager = make_manager(tmp_path, manifest, source=FakeSource())
    result = manager.dry_run()
    assert result["dry_run"] is True
    assert any(p["project_id"] == "demo" for p in result["plans"])


def test_no_stable_release_status(tmp_path):
    root, manifest = make_project(tmp_path, extra={"release_only": True})
    source = FakeSource(available={
        "ref": "abcdef012345", "ref_type": "commit", "version": None,
        "release_tag": None, "published_at": None, "url": "x",
        "development": True,
        "note": "Repository reachable, but no stable release is published.",
    })
    manager = make_manager(tmp_path, manifest, source=source)
    plan = manager.check("demo")
    assert plan["status"] == "no-stable-release"
    assert plan["would_update"] is False
    assert plan["requires_confirmation"] is True
    assert "no stable release" in (plan["note"] or "")

    result = manager.update("demo", confirm=True)
    assert result["ok"] is False
    assert result["result"] == "no-stable-release"
    # a development build is never applied; the install is untouched
    assert (root / "components" / "demo" / "VERSION").read_text() == "1.0.0"
    # update-all reports it without attempting an update
    res = manager.update_all(confirm=True)
    entry = [s for s in res["summary"] if s["project_id"] == "demo"][0]
    assert entry["status"] == "no-stable-release"


def test_missing_status(tmp_path):
    root, manifest = make_project(tmp_path)
    install_dir = root / "components" / "demo"
    shutil.rmtree(install_dir)
    manager = make_manager(tmp_path, manifest, source=FakeSource())
    plan = manager.check("demo")
    assert plan["status"] == "missing"
    assert plan["would_update"] is True
    assert plan["requires_confirmation"] is True


def test_installed_status_for_unmanaged_install(tmp_path):
    root, manifest = make_project(tmp_path)
    manager = make_manager(tmp_path, manifest, source=FakeSource())
    plan = manager.check("demo")
    assert plan["status"] == "installed"
    assert plan["would_update"] is True
    assert plan["requires_confirmation"] is True


# ---------------------------------------------------------------------------
# successful update
# ---------------------------------------------------------------------------

def test_successful_update(tmp_path):
    root, manifest = make_project(tmp_path)
    install_dir = root / "components" / "demo"
    source = FakeSource()
    logs = []
    manager = make_manager(tmp_path, manifest, source=source, log=lambda l, s, m: logs.append((l, m)))

    result = manager.update("demo", confirm=True)
    assert result["ok"] is True
    assert result["result"] == "success"
    assert (install_dir / "VERSION").read_text().startswith("2.0.0")
    meta = json.loads((install_dir / ".jpnh-update.json").read_text())
    assert meta["ref"] == source.available["ref"]
    assert meta["version"] == "2.0.0"
    history = manager.history.list()
    assert history and history[0]["result"] == "success"
    assert history[0]["backup_id"]
    assert manager.status_entry(manifest)["status"] == "up-to-date"
    assert not any("secret" in m.lower() for _, m in logs)


def test_update_refuses_untracked_without_confirmation(tmp_path):
    root, manifest = make_project(tmp_path)
    manager = make_manager(tmp_path, manifest, source=FakeSource())
    with pytest.raises(UpdateManagerError) as exc:
        manager.update("demo", confirm=False)
    assert "requires confirmation" in str(exc.value)


# ---------------------------------------------------------------------------
# failed update + auto rollback
# ---------------------------------------------------------------------------

def test_download_failure_returns_clean_error(tmp_path):
    root, manifest = make_project(tmp_path)
    manager = make_manager(tmp_path, manifest, source=FakeSource(fail="download"))
    result = manager.update("demo", confirm=True)
    assert result["ok"] is False
    assert result["result"] == "failed"
    assert "download failed" in result["error"]
    assert result["backup_id"]
    history = manager.history.list()
    assert history[0]["result"] == "failed"
    assert "upstream" not in (history[0]["error"] or "")  # message is stable/human


def test_apply_failure_auto_rollback(tmp_path):
    root, manifest = make_project(tmp_path)
    install_dir = root / "components" / "demo"
    source = FakeSource()
    manager = make_manager(tmp_path, manifest, source=source)
    original = (install_dir / "VERSION").read_text()

    def broken_build(project):
        return {"ran": True, "failed": True, "error": "flutter build exploded"}
    manager._build = broken_build

    result = manager.update("demo", confirm=True)
    assert result["ok"] is False
    assert result["result"] == "rolled-back"
    assert result["rollback"]["restored"] is True
    # install dir restored to pre-update content
    assert (install_dir / "VERSION").read_text() == original
    history = manager.history.list()
    assert history[0]["result"] == "rolled-back"
    assert history[0]["rollback_status"] == "ok"


def test_staged_content_missing_required_file_rolls_back(tmp_path):
    root, manifest = make_project(tmp_path)
    install_dir = root / "components" / "demo"
    source = FakeSource(missing_required=["VERSION"])
    manager = make_manager(tmp_path, manifest, source=source)
    original = (install_dir / "VERSION").read_text()
    result = manager.update("demo", confirm=True)
    assert result["ok"] is False
    assert (install_dir / "VERSION").read_text() == original


# ---------------------------------------------------------------------------
# health checks
# ---------------------------------------------------------------------------

def test_health_check_required_files(tmp_path):
    root, manifest = make_project(tmp_path)
    health = HealthCheckManager(root=root)
    result = health.run(manifest)
    assert result["ok"] is True
    (root / "components" / "demo" / "VERSION").unlink()
    assert health.run(manifest)["ok"] is False


def test_health_version_consistency(tmp_path):
    root, manifest = make_project(tmp_path, version="1.0.0",
                                  extra={"health_checks": ["version-consistency"]})
    health = HealthCheckManager(root=root)
    assert health.run(manifest, expected_version="1.0.0")["ok"] is True
    assert health.run(manifest, expected_version="2.0.0")["ok"] is False


# ---------------------------------------------------------------------------
# update all
# ---------------------------------------------------------------------------

def _seed_tracked(manager, manifest, root):
    install_dir = root / "components" / "demo"
    manager._write_metadata(manifest, {
        "ref": "oldref", "ref_type": "commit", "version": "1.0.0",
        "installed_fingerprint": _fingerprint(install_dir, manifest),
        "installed_hashes": _hashes(install_dir, manifest),
    })


def test_update_all_summary(tmp_path):
    root, manifest = make_project(tmp_path)
    registry = ProjectRegistry()
    registry.register(manifest)

    # unsafe project (installed but unmanaged) -> skipped
    unsafe_dir = root / "components" / "unsafe"
    unsafe_dir.mkdir(parents=True)
    (unsafe_dir / "VERSION").write_text("1.0.0")
    unsafe_manifest = ProjectManifest.from_dict({
        "id": "unsafe", "name": "Unsafe", "source_type": "github",
        "repository": "owner/unsafe", "install_path": "components/unsafe",
        "version_detection": "version_file", "current_version_file": "VERSION",
        "required_files": ["VERSION"], "health_checks": ["required-files"],
    })
    registry.register(unsafe_manifest)

    manager = UpdateManager(
        registry=registry, state=UpdateState(), history=UpdateHistory(),
        backup=BackupManager(root=root), health=HealthCheckManager(root=root),
        root=root,
    )
    _seed_tracked(manager, manifest, root)
    # both projects resolve through the same fake source
    manager.source_for = lambda m: FakeSource()

    result = manager.update_all(confirm=True)
    summary = {s["project_id"]: s for s in result["summary"]}
    assert summary["demo"]["status"] == "success"
    assert summary["unsafe"]["status"] == "skipped"
    assert "not tracked" in summary["unsafe"]["error"]


def test_update_all_dry_run_no_changes(tmp_path):
    root, manifest = make_project(tmp_path)
    manager = make_manager(tmp_path, manifest, source=FakeSource())
    _seed_tracked(manager, manifest, root)
    before = (root / "components" / "demo" / "VERSION").read_text()
    result = manager.update_all(dry_run=True)
    assert result["dry_run"] is True
    assert (root / "components" / "demo" / "VERSION").read_text() == before


# ---------------------------------------------------------------------------
# rollback (manual)
# ---------------------------------------------------------------------------

def test_manual_rollback(tmp_path):
    root, manifest = make_project(tmp_path)
    install_dir = root / "components" / "demo"
    source = FakeSource()
    manager = make_manager(tmp_path, manifest, source=source)
    manager.update("demo", confirm=True)
    backup_id = manager.history.list()[0]["backup_id"]
    assert (install_dir / "VERSION").read_text().startswith("2.0.0")

    result = manager.rollback(backup_id)
    assert result["ok"] is True
    assert (install_dir / "VERSION").read_text() == "1.0.0"
    history = manager.history.list()
    assert history[0]["result"] == "rolled-back"

    with pytest.raises(UpdateManagerError):
        manager.rollback("nope-missing-00000000")


# ---------------------------------------------------------------------------
# JPNH core staging
# ---------------------------------------------------------------------------

def test_jpnh_core_update_stages_only(tmp_path):
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
    })
    manager = UpdateManager(root=root)
    manager.source_for = lambda m: FakeSource(
        available={"ref": "v0.2.0", "ref_type": "tag", "version": "0.2.0",
                   "release_tag": "v0.2.0", "published_at": None,
                   "url": "x", "development": False})

    result = manager.update("jpnh-core", confirm=True)
    assert result["result"] == "staged"
    assert result["ok"] is True
    # the running checkout is never touched
    assert (root / "VERSION").read_text() == "0.1.0"
    state = manager.state.get("jpnh-core")
    assert state["staged_ref"] == "v0.2.0"
    history = manager.history.list()
    assert history[0]["result"] == "staged"


# ---------------------------------------------------------------------------
# sources: GitHub
# ---------------------------------------------------------------------------

class FakeGithubTransport:
    """Records request kwargs for proxy-env assertions."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, params=None, **kwargs):
        self.calls.append({"url": url, "params": params, "kwargs": kwargs})
        return self.responses.get(url, _FakeResponse(404))


class _FakeResponse:
    def __init__(self, status_code, json=None, text=""):
        self.status_code = status_code
        self._json = json or {}
        self.text = text

    def json(self):
        return self._json


def fake_api_json(transport):
    """Mimic GitHubSource.api_json: raise on non-200, return JSON otherwise."""

    def api_json(url, params=None):
        resp = transport.get(url, params=params)
        if resp.status_code in (401, 403):
            raise UpdateSourceError("GitHub rejected the request (rate limit or auth). "
                                    "Retry later or set a GitHub token in the vault.")
        if resp.status_code == 429:
            raise UpdateSourceError("GitHub rate limit reached. Retry in a few minutes.")
        if resp.status_code == 404:
            raise UpdateSourceError("GitHub resource not found")
        if 500 <= resp.status_code < 600:
            raise UpdateSourceError(f"GitHub server error (HTTP {resp.status_code})")
        if resp.status_code != 200:
            raise UpdateSourceError(f"GitHub returned HTTP {resp.status_code}")
        return resp.json()

    return api_json


def test_github_source_check_release(tmp_path):
    repo = "owner/demo"
    responses = {
        f"https://api.github.com/repos/{repo}": _FakeResponse(200, {"default_branch": "main"}),
        f"https://api.github.com/repos/{repo}/releases/latest": _FakeResponse(200, {"tag_name": "v2.0.0", "published_at": "2026-01-01T00:00:00Z"}),
    }
    transport = FakeGithubTransport(responses)
    source = GitHubSource(http=transport)
    source.api_json = fake_api_json(transport)
    source.raw_file = lambda repo, ref, path: "name: x\nversion: 2.0.0\n"
    manifest = ProjectManifest.from_dict({
        "id": "demo", "name": "Demo", "source_type": "github",
        "repository": repo, "release_only": True,
        "version_detection": "file", "current_version_file": "pubspec.yaml",
    })
    info = source.check_available(manifest)
    assert info["ref"] == "v2.0.0"
    assert info["version"] == "2.0.0"
    assert info["ref_type"] == "tag"


def test_github_source_dev_fallback(tmp_path):
    repo = "owner/demo"
    responses = {
        f"https://api.github.com/repos/{repo}": _FakeResponse(200, {"default_branch": "main"}),
        f"https://api.github.com/repos/{repo}/releases/latest": _FakeResponse(404),
        f"https://api.github.com/repos/{repo}/tags": _FakeResponse(200, []),
        f"https://api.github.com/repos/{repo}/commits/main": _FakeResponse(200, {"sha": "feedface1234"}),
    }
    transport = FakeGithubTransport(responses)
    source = GitHubSource(http=transport)
    source.api_json = fake_api_json(transport)
    source.raw_file = lambda repo, ref, path: None
    manifest = ProjectManifest.from_dict({
        "id": "demo", "name": "Demo", "source_type": "github",
        "repository": repo, "release_only": True, "branch": "main",
    })
    info = source.check_available(manifest)
    assert info["ref"] == "feedface1234"
    assert info["development"] is True


def test_github_source_not_found_error():
    transport = FakeGithubTransport({})
    source = GitHubSource(http=transport)
    source.api_json = fake_api_json(transport)
    with pytest.raises(UpdateSourceError) as exc:
        source.check_available(ProjectManifest.from_dict({
            "id": "xx", "name": "x", "source_type": "github", "repository": "a/b",
            "branch": "main"}))
    assert "not found" in str(exc.value)
    assert "not publicly accessible" in str(exc.value)


def test_github_source_reachable_no_release(tmp_path):
    repo = "owner/demo"
    responses = {
        f"https://api.github.com/repos/{repo}": _FakeResponse(200, {"default_branch": "main"}),
        f"https://api.github.com/repos/{repo}/releases/latest": _FakeResponse(404),
        f"https://api.github.com/repos/{repo}/tags": _FakeResponse(200, []),
        f"https://api.github.com/repos/{repo}/commits/main": _FakeResponse(200, {"sha": "feedface1234"}),
    }
    transport = FakeGithubTransport(responses)
    source = GitHubSource(http=transport)
    source.api_json = fake_api_json(transport)
    source.raw_file = lambda repo, ref, path: None
    manifest = ProjectManifest.from_dict({
        "id": "demo", "name": "Demo", "source_type": "github",
        "repository": repo, "release_only": True,
    })
    info = source.check_available(manifest)
    assert info["development"] is True
    assert info["ref"] == "feedface1234"
    assert info["version"] is None
    assert "no stable release" in (info.get("note") or "")


def test_github_source_branch_not_found():
    repo = "owner/demo"
    responses = {
        f"https://api.github.com/repos/{repo}": _FakeResponse(200, {"default_branch": "main"}),
        f"https://api.github.com/repos/{repo}/commits/main": _FakeResponse(404),
    }
    transport = FakeGithubTransport(responses)
    source = GitHubSource(http=transport)
    source.api_json = fake_api_json(transport)
    with pytest.raises(UpdateSourceError) as exc:
        source.check_available(ProjectManifest.from_dict({
            "id": "demo", "name": "Demo", "source_type": "github",
            "repository": repo}))
    assert "branch or ref" in str(exc.value)


def test_github_source_rate_limit_and_server_errors():
    repo = "owner/demo"
    cases = [
        (429, "rate limit"),
        (403, "rejected"),
        (500, "server error"),
        (503, "server error"),
    ]
    for status, expected in cases:
        transport = FakeGithubTransport({
            f"https://api.github.com/repos/{repo}": _FakeResponse(status),
        })
        source = GitHubSource(http=transport)
        source.api_json = fake_api_json(transport)
        with pytest.raises(UpdateSourceError) as exc:
            source.check_available(ProjectManifest.from_dict({
                "id": "demo", "name": "Demo", "source_type": "github",
                "repository": repo}))
        assert expected in str(exc.value).lower(), (status, str(exc.value))


def test_github_source_malformed_json():
    repo = "owner/demo"
    source = GitHubSource(http=FakeGithubTransport({}))

    class BadJson:
        status_code = 200
        def json(self):
            raise ValueError("no json")
    source._http.get = lambda url, **kw: BadJson()
    with pytest.raises(UpdateSourceError) as exc:
        source.check_available(ProjectManifest.from_dict({
            "id": "demo", "name": "Demo", "source_type": "github",
            "repository": repo}))
    assert "unparseable" in str(exc.value)


# ---------------------------------------------------------------------------
# proxy environment handling
# ---------------------------------------------------------------------------

def test_build_client_honours_proxy_env(monkeypatch):
    import httpx as real_httpx
    from backend.updates import sources as mod

    # With a normal http proxy env, the client is constructed with trust_env
    recorded = {}

    class Recorder(real_httpx.Client):
        def __init__(self, *args, **kwargs):
            recorded["kwargs"] = kwargs
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(mod.httpx, "Client", Recorder)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:10808")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:10808")
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.delenv("all_proxy", raising=False)
    client = _build_client(10)
    assert recorded["kwargs"]["trust_env"] is True
    client.close()


def test_build_client_falls_back_on_bad_proxy_scheme(monkeypatch):
    import httpx as real_httpx
    from backend.updates import sources as mod

    class Exploding(real_httpx.Client):
        def __init__(self, *args, **kwargs):
            if kwargs.get("trust_env") is True:
                raise ValueError("Unknown scheme for proxy URL")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(mod.httpx, "Client", Exploding)
    monkeypatch.setenv("ALL_PROXY", "socks://127.0.0.1:10808")
    client = _build_client(10)  # must not raise
    assert client is not None
    client.close()


# ---------------------------------------------------------------------------
# secrets never appear in logs
# ---------------------------------------------------------------------------

def test_redaction_removes_credentials():
    from backend.services.logging import redact
    assert "s3cret" not in redact("https://user:s3cret@proxy.example.com/path")
    assert "TOPSECRET" not in redact("vless://abc-TOPSECRET@1.2.3.4:443#x")
    assert "hideme" not in redact("trojan://hideme@1.2.3.4:443#t")
    assert "p@ssw0rd" not in redact("vmess://x?password=p@ssw0rd&other=1")


def test_update_failure_log_has_no_secret(tmp_path):
    root, manifest = make_project(tmp_path)
    collector = []
    source = FakeSource(fail="download")
    manager = make_manager(tmp_path, manifest, source=source,
                           log=lambda level, src, msg: collector.append(msg))
    result = manager.update("demo", confirm=True)
    joined = "\n".join(collector) + "\n" + json.dumps(result)
    assert "secret" not in joined.lower()
    history = manager.history.list()
    assert "token" not in json.dumps(history).lower()


# ---------------------------------------------------------------------------
# network checker helpers / parse
# ---------------------------------------------------------------------------

def test_parse_pubspec_version(tmp_path):
    p = tmp_path / "pubspec.yaml"
    p.write_text("name: rdnbenet\nversion: 1.5.0+3\n")
    assert parse_version_from_file(p) == "1.5.0"
    v = tmp_path / "VERSION"
    v.write_text("0.2.0\n")
    assert parse_version_from_file(v) == "0.2.0"


# ---------------------------------------------------------------------------
# malicious archives
# ---------------------------------------------------------------------------

def _make_tar(tmp_path, members):
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content, kind in members:
            if kind == "dir":
                info = tarfile.TarInfo(name)
                info.type = tarfile.DIRTYPE
                tar.addfile(info)
            elif kind == "symlink":
                info = tarfile.TarInfo(name)
                info.type = tarfile.SYMTYPE
                info.linkname = content
                tar.addfile(info)
            else:
                data = content.encode()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    path = tmp_path / "bad.tar.gz"
    path.write_bytes(buf.read())
    return path


def test_build_scripts_refuse_win_cross_compile():
    """Flutter/PyInstaller cannot cross-compile for Windows on Linux; the build
    scripts must refuse rather than silently producing a broken bundle."""
    if sys.platform == "win32":
        pytest.skip("only meaningful on non-Windows hosts")
    import shutil
    import subprocess
    if shutil.which("node") is None:
        pytest.skip("node not available")
    root = Path(__file__).resolve().parents[1]
    for script in ("build-backend.mjs", "build-network-checker.mjs"):
        r = subprocess.run(
            ["node", str(root / "desktop" / "build" / "scripts" / script), "win"],
            capture_output=True, text=True)
        assert r.returncode != 0, f"{script} should refuse win-on-linux"
        assert "cannot cross-compile" in (r.stderr + r.stdout).lower(), script


def test_extract_rejects_path_traversal(tmp_path):
    from backend.updates.sources import _extract_tarball
    archive = _make_tar(tmp_path, [("../escape.txt", "pwned", "file")])
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(UpdateSourceError):
        _extract_tarball(archive, dest)
    assert not (tmp_path / "escape.txt").exists()


def test_extract_rejects_symlink(tmp_path):
    from backend.updates.sources import _extract_tarball
    archive = _make_tar(tmp_path, [("link", "/etc/passwd", "symlink")])
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(UpdateSourceError):
        _extract_tarball(archive, dest)


def test_extract_rejects_absolute_path(tmp_path):
    from backend.updates.sources import _extract_tarball
    archive = _make_tar(tmp_path, [("/tmp/abs-write", "x", "file")])
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(UpdateSourceError):
        _extract_tarball(archive, dest)


def test_extract_accepts_normal_tree(tmp_path):
    from backend.updates.sources import _extract_tarball
    archive = _make_tar(tmp_path, [
        ("repo/pubspec.yaml", "version: 9.9.9\n", "file"),
        ("repo/lib/main.dart", "void main(){}", "file"),
    ])
    dest = tmp_path / "out"
    dest.mkdir()
    _extract_tarball(archive, dest)
    assert (dest / "repo" / "pubspec.yaml").read_text().startswith("version:")


def test_local_source_rejects_update():
    source = LocalSource()
    manifest = ProjectManifest.from_dict({"id": "local", "name": "Local",
                                          "source_type": "local"})
    with pytest.raises(UpdateSourceError):
        source.download(manifest, "x")
    assert source.check_available(manifest)["ref"] is None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _fingerprint(directory, manifest):
    from backend.updates.sources import tree_fingerprint
    return tree_fingerprint(directory, manifest)


def _hashes(directory, manifest):
    from backend.updates.sources import file_hashes
    return file_hashes(directory, manifest)


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------

@pytest.fixture()
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


def test_api_projects_and_updates(api_client):
    r = api_client.get("/projects")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()["projects"]}
    assert {"jpnh-core", "network-checker"} <= ids

    r = api_client.get("/updates")
    assert r.status_code == 200
    assert r.json()["errors"] == []


def test_api_history_and_backups_empty(api_client):
    assert api_client.get("/updates/history").json()["history"] == []
    assert api_client.get("/updates/backups").json()["backups"] == []


def test_api_rollback_unknown_backup(api_client):
    r = api_client.post("/updates/rollback/nope-20260819")
    assert r.status_code == 400


def test_api_update_unknown_project(api_client):
    r = api_client.post("/updates/nope/update", json={"project_id": "nope"})
    assert r.status_code == 400


def test_api_dry_run_uses_state_updates(api_client, monkeypatch):
    # wired through the app_state singleton's update manager
    from backend.api.v1 import deps
    manager = deps.app_state.updates

    class StubSource:
        def check_available(self, manifest):
            return {"ref": "v9.0.0", "ref_type": "tag", "version": "9.0.0",
                    "release_tag": "v9.0.0", "published_at": None, "url": "x",
                    "development": False}
    manager.source_for = lambda m: StubSource()
    r = api_client.post("/updates/dry-run", json={})
    assert r.status_code == 200
    plans = {p["project_id"]: p for p in r.json()["plans"]}
    assert plans["jpnh-core"]["available"]["version"] == "9.0.0"


def test_api_update_unsafe_requires_confirmation(api_client, monkeypatch):
    from backend.api.v1 import deps
    manager = deps.app_state.updates

    class StubSource:
        def check_available(self, manifest):
            return {"ref": "abcdef012345", "ref_type": "commit", "version": "1.6.0",
                    "release_tag": None, "published_at": None, "url": "x",
                    "development": False}
    manager.source_for = lambda m: StubSource()
    # network-checker is installed but unmanaged -> confirmation required
    r = api_client.post("/updates/network-checker/update",
                        json={"project_id": "network-checker", "confirm": False})
    assert r.status_code == 400
    assert "requires confirmation" in r.json()["detail"]


def test_api_rollback_invalid_backup_id(api_client):
    r = api_client.post("/updates/rollback/A!")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_status(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("JPNH_DATA_DIR", str(tmp_path / "data"))
    from backend.updates import cli
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "network-checker" in out


def test_cli_rollback_missing_returns_error(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("JPNH_DATA_DIR", str(tmp_path / "data"))
    from backend.updates import cli
    assert cli.main(["rollback", "nope-20260819"]) == 1
    assert "error" in capsys.readouterr().err


def test_cli_dry_run_uses_manager(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("JPNH_DATA_DIR", str(tmp_path / "data"))
    from backend.updates import cli
    import backend.updates.cli as cli_mod

    captured = {}

    class StubManager:
        def dry_run(self, project_id=None):
            captured["called"] = True
            return {"dry_run": True, "plans": [
                {"project_id": "demo", "name": "Demo", "status": "update-available",
                 "would_update": True, "current": {"version": "1.0.0"},
                 "available": {"version": "2.0.0"},
                 "local_changes": {"detected": False},
                 "requires_confirmation": False, "build_required": False,
                 "error": None}]}

    monkeypatch.setattr(cli_mod, "UpdateManager", lambda **kw: StubManager())
    assert cli_mod.main(["dry-run"]) == 0
    assert captured["called"] is True
    assert "demo" in capsys.readouterr().out


def test_cli_logs_redact_credentials(tmp_path, capsys, monkeypatch):
    """CLI output (stdout/stderr) must never echo credentials."""
    from backend.updates import cli
    cli._log("WARNING", "updates", "proxy error: http://user:sup3rs3cret@proxy:8080")
    cli._log("ERROR", "updates", "failed https://x?token=TOPSECRETVALUE")
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "sup3rs3cret" not in out
    assert "TOPSECRETVALUE" not in out