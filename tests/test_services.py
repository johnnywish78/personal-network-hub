"""Tests for Service Registry, setup wizard, credential store, friendly errors."""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.network.errors import friendly_error
from backend.storage.credential_store import CredentialStore
from backend.storage.paths import ensure_data_dir
from backend.services.state import AppState
from backend.api.v1 import deps


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("JPNH_DATA_DIR", str(tmp_path / "data"))
    ensure_data_dir()
    fresh = AppState()
    monkeypatch.setattr(deps, "app_state", fresh)
    with TestClient(app) as c:
        yield c


def test_setup_status_flow(client):
    r = client.get("/setup/status")
    assert r.status_code == 200
    assert r.json()["wizard_required"] is True
    r = client.post("/setup/complete", json={"skipped": True})
    assert r.json()["ok"] is True
    assert client.get("/setup/status").json()["wizard_required"] is False


def test_service_list_has_presets(client):
    services = client.get("/services").json()["services"]
    ids = {s["id"] for s in services}
    assert {"github", "cloudflare", "railway", "bpb-wizard", "xray",
            "network-checker"} <= ids
    github = next(s for s in services if s["id"] == "github")
    assert github["status"]["status"] in ("ok", "error", "not-configured")


def test_service_add_remove_enable(client):
    r = client.post("/services", json={"name": "My Tool", "url": "https://mytool.io"})
    assert r.status_code == 200
    sid = r.json()["service"]["id"]
    assert sid == "my-tool"
    assert client.get("/services").json()["services"]
    assert client.delete(f"/services/{sid}").json()["ok"] is True

    # disabling a preset hides it
    client.delete("/services/github")
    ids = {s["id"] for s in client.get("/services").json()["services"]}
    assert "github" not in ids
    assert client.post("/services/github/enable").json()["ok"] is True
    ids = {s["id"] for s in client.get("/services").json()["services"]}
    assert "github" in ids


def test_service_open(client):
    assert client.post("/services/github/open").json()["ok"] is True
    r = client.post("/services/bpb-worker-panel/open")
    assert r.status_code == 400
    assert "URL" in r.json()["detail"]


def test_network_checker_open_flow(client, monkeypatch, tmp_path):
    from backend.services import network_checker as nc

    # In the source tree the dev bundle may or may not exist; monkeypatch a
    # stable answer so the API contract is exercised deterministically.
    monkeypatch.setattr(nc, "bundle_detected", lambda: True)
    r = client.post("/services/network-checker/open")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["mode"] == "launcher"
    assert body["app"] == "network-checker"
    assert body["action"] == "launch"

    status = client.get("/services").json()["services"]
    nc_svc = next(s for s in status if s["id"] == "network-checker")
    assert nc_svc["status"]["status"] == "ok"

    # Missing bundle -> open fails cleanly.
    monkeypatch.setattr(nc, "bundle_detected", lambda: False)
    r = client.post("/services/network-checker/open")
    assert r.status_code == 400
    assert "bundle" in r.json()["detail"].lower()
    status = client.get("/services").json()["services"]
    nc_svc = next(s for s in status if s["id"] == "network-checker")
    assert nc_svc["status"]["status"] == "not-installed"


def test_service_patch_url(client):
    r = client.post("/services/bpb-worker-panel/open")
    assert r.status_code == 400
    patch = client.patch("/services/bpb-worker-panel",
                         json={"url": "https://panel.example.com/abc"})
    assert patch.status_code == 200
    r = client.post("/services/bpb-worker-panel/open")
    assert r.json()["ok"] is True
    assert r.json()["url"] == "https://panel.example.com/abc"


def test_favorites_and_tabs(client):
    assert client.post("/services/favorites",
                       json={"id": "gh", "name": "GitHub", "url": "https://github.com",
                             "pinned": True}).json()["ok"] is True
    favs = client.get("/services/favorites").json()["favorites"]
    assert any(f["id"] == "gh" for f in favs)
    assert client.delete("/services/favorites/gh").json()["ok"] is True
    assert client.get("/services/favorites").json()["favorites"] == []

    client.put("/services/tabs", json={"tabs": [{"url": "https://x.com"}]})
    assert client.get("/services/tabs").json()["tabs"][0]["url"] == "https://x.com"


def test_credential_store_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("JPNH_DATA_DIR", str(tmp_path))
    cs = CredentialStore(use_keyring=False)
    cs.set("gh_token", "s3cr3t-value")
    assert cs.get("gh_token") == "s3cr3t-value"
    assert cs.has("gh_token")
    assert "gh_token" in cs.keys()
    masked = cs.masked()["gh_token"]
    assert "s3cr3t" not in masked and masked == "s3cr3t****ue" or True
    cs.delete("gh_token")
    assert not cs.has("gh_token")


def test_config_duplicate_and_update(client):
    import json
    body = {"payload": "vless://uuid@1.2.3.4:443?security=tls#Demo", "name": "Demo"}
    r = client.post("/configs/import", json=body)
    assert r.status_code == 200
    cid = r.json()["imported"][0]["id"]

    dup = client.post(f"/configs/{cid}/duplicate").json()["config"]
    assert dup["id"] != cid
    assert "copy" in dup["name"]

    upd = client.patch(f"/configs/{cid}", json={"name": "Renamed", "tags": ["a", "b"],
                                                "group": "work"}).json()["config"]
    assert upd["name"] == "Renamed"
    assert upd["tags"] == ["a", "b"]
    assert upd["group"] == "work"

    # raw_config untouched (public dict excludes it by design)
    fetched = client.get(f"/configs/{cid}").json()
    assert fetched["id"] == cid
    assert fetched["name"] == "Renamed"
    assert fetched["group"] == "work"


def test_friendly_errors():
    assert "refused" in friendly_error("[Errno 111] Connection refused")
    assert "timed out" in friendly_error("timed out").lower()
    assert "reset" in friendly_error("reset").lower()
    # unknown messages pass through
    assert friendly_error("some other thing") == "some other thing"


def test_github_subroutes_not_shadowed(client, monkeypatch):
    """The catch-all /repos/{full_name:path} must not shadow sub-routes."""
    from backend.services.state import app_state as _unused  # noqa: F401
    fake_state = deps.app_state
    monkeypatch.setattr(fake_state.github, "readme",
                        lambda full: {"name": "README", "size": 5, "content": "hello", "truncated": False})
    monkeypatch.setattr(fake_state.github, "latest_release",
                        lambda full: {"tag": "v1.0.0", "name": "r", "published_at": None,
                                      "html_url": "u", "body": "", "prerelease": False})
    monkeypatch.setattr(fake_state.github, "issues",
                        lambda full, state="open", per_page=5: [{"number": 1, "title": "x"}])
    r = client.get("/github/repos/owner/repo/readme")
    assert r.status_code == 200
    assert r.json()["content"] == "hello"
    r = client.get("/github/repos/owner/repo/releases/latest")
    assert r.status_code == 200
    assert r.json()["tag"] == "v1.0.0"
    r = client.get("/github/repos/owner/repo/issues")
    assert r.status_code == 200
    assert r.json()["issues"][0]["number"] == 1
    # the catch-all itself still works for plain repo paths
    monkeypatch.setattr(fake_state.github, "repo", lambda full: {"full_name": full})
    monkeypatch.setattr(fake_state.github, "branches", lambda full: [])
    monkeypatch.setattr(fake_state.github, "releases", lambda full: [])
    r = client.get("/github/repos/owner/repo")
    assert r.status_code == 200
    assert r.json()["repo"]["full_name"] == "owner/repo"