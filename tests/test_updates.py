"""Tests for the Update Manager / Project Manager subsystem.

Covers: version comparison, registry, sources, backup/restore, rollback,
dry-run, successful/failed updates, health checks, Update All, proxy env
handling, secrets-in-logs, and malformed manifests. Network calls are
always mocked — no test touches a real remote.
"""

from __future__ import annotations

import json
import shutil
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
                                     _build_client, parse_version_from_file)
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

    # unsafe project (untracked) -> skipped
    unsafe_root = tmp_path / "root2"
    unsafe_dir = unsafe_root / "components" / "unsafe"
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
    assert "untracked" in summary["unsafe"]["error"]


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
        if resp.status_code == 404:
            raise UpdateSourceError("GitHub resource not found")
        if resp.status_code == 401 or resp.status_code == 403:
            raise UpdateSourceError("GitHub rejected the request")
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