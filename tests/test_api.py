"""API contract tests using the FastAPI TestClient."""

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None

pytestmark = pytest.mark.skipif(TestClient is None, reason="requires starlette TestClient")


@pytest.fixture(scope="module")
def client():
    from backend.main import app
    with TestClient(app) as c:
        yield c


def test_ping(client):
    r = client.get("/ping")
    assert r.status_code == 200
    assert r.json()["pong"] is True


def test_version(client):
    r = client.get("/version")
    assert r.json()["version"] == "0.1.0"
    assert r.json()["codename"] == "JPNH"


def test_dashboard(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert "internet" in data
    assert "services" in data
    assert "configs" in data
    assert "xray" in data
    assert "clients" in data


def test_providers_list(client):
    r = client.get("/providers")
    names = [p["name"] for p in r.json()["providers"]]
    assert "rvg" in names
    assert "zeus" in names


def test_config_import_and_list(client):
    uri = ("vless://550e8400-e29b-41d4-a716-446655440000@api.example.com:443"
           "?security=tls&type=ws&host=h.example.com&path=/ws#API-Test")
    r = client.post("/configs/import", json={"payload": uri, "provider": "RVG"})
    assert r.status_code == 200
    body = r.json()
    assert body["imported"]
    cid = body["imported"][0]["id"]

    listed = client.get("/configs").json()
    assert any(c["id"] == cid for c in listed["configs"])

    parsed = client.post("/configs/parse", json={"payload": uri}).json()
    assert parsed["ok"] is True
    assert parsed["results"][0]["validation_ok"] is True

    uri_resp = client.get(f"/configs/{cid}/uri")
    assert uri_resp.json()["uri"].startswith("vless://")

    qr_resp = client.get(f"/configs/{cid}/qr")
    assert qr_resp.json()["ok"] is True
    assert len(qr_resp.json()["png_base64"]) > 100

    exp = client.get(f"/configs/{cid}/export?fmt=json")
    assert exp.json()["ok"] is True

    deleted = client.delete(f"/configs/{cid}")
    assert deleted.json()["ok"] is True


def test_config_validate_endpoint(client):
    uri = "vless://550e8400-e29b-41d4-a716-446655440000@x.com:443#v"
    r = client.post("/configs/import", json={"payload": uri})
    cid = r.json()["imported"][0]["id"]
    v = client.post(f"/configs/{cid}/validate").json()
    assert v["validation"]["valid"] is True
    client.delete(f"/configs/{cid}")


def test_unknown_provider_404(client):
    assert client.get("/providers/nope").status_code == 404


def test_auth_status_masked(client):
    r = client.get("/auth/status")
    assert r.status_code == 200
    assert "cloudflare" in r.json()["configured"]


def test_cloudflare_status_without_token(client):
    r = client.get("/cloudflare/status")
    body = r.json()
    assert "configured" in body


def test_settings_roundtrip(client):
    client.post("/settings", json={"key": "theme", "value": "light"})
    assert client.get("/settings").json()["settings"]["theme"] == "light"
    client.post("/settings", json={"key": "theme", "value": "dark"})


def test_logs_endpoints(client):
    r = client.get("/logs")
    assert r.status_code == 200
    assert "logs" in r.json()
