"""Network Checker native integration tests.

Covers the /checker/* API routes for the tools ported from the GPL-3.0
mirarr-app/network-checker project.
"""

import pytest

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None

pytestmark = pytest.mark.skipif(TestClient is None, reason="requires starlette TestClient")

VLESS_A = ("vless://550e8400-e29b-41d4-a716-446655440000@entry.example.com:443"
           "?security=tls&type=ws&host=h.example.com&path=/ws&fp=chrome#Entry")
VLESS_B = ("vless://550e8400-e29b-41d4-a716-446655440000@exit.example.com:443"
           "?security=tls&type=ws&host=h.example.com&path=/ws#Exit")


@pytest.fixture(scope="module")
def client():
    from backend.main import app
    with TestClient(app) as c:
        yield c


def test_checker_metadata(client):
    r = client.get("/checker/metadata")
    assert r.status_code == 200
    defaults = r.json()["defaults"]
    for tool in ("domain_check", "dns_latency", "sni_spoof_check",
                 "cloudflare_fix", "chain"):
        assert tool in defaults


def test_checker_cloudflare_fix(client):
    r = client.post("/checker/cloudflare-fix", json={"links": VLESS_A})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["errors"] == []
    fixed = body["results"][0]
    assert fixed["remarks"] == "Entry-custom"
    assert fixed["address"] == "entry.example.com"
    assert "dns" in fixed["json_config"]


def test_checker_cloudflare_fix_invalid_link(client):
    r = client.post("/checker/cloudflare-fix", json={"links": "trojan://x@1.2.3.4:443#b"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert len(body["errors"]) == 1


def test_checker_cloudflare_fix_empty(client):
    r = client.post("/checker/cloudflare-fix", json={"links": ""})
    assert r.status_code == 400


def test_checker_chain(client):
    r = client.post("/checker/chain", json={"links": f"{VLESS_A}\n{VLESS_B}"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["hop_count"] == 2
    assert body["json"].startswith("{")
    assert "socks-in" in body["profile"]["inbounds"][0]["tag"]


def test_checker_chain_needs_two(client):
    r = client.post("/checker/chain", json={"links": VLESS_A})
    assert r.status_code == 400


def test_checker_sni_spoof_check(client):
    r = client.post("/checker/sni-spoof-check", json={
        "targets": "example.com", "ports": [443], "timeout": 2, "retries": 1,
        "concurrency": 3, "enable_ip_check": False,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["results"][0]["target"] == "example.com"


def test_checker_sni_spoof_check_bad_timeout(client):
    r = client.post("/checker/sni-spoof-check", json={
        "targets": "example.com", "ports": [443], "timeout": -1,
    })
    assert r.status_code == 400


def test_checker_domain_check(client):
    r = client.post("/checker/domain-check", json={
        "targets": ["example.com"], "timeout": 3, "concurrency": 5,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert "results" in body


def test_checker_dns_latency(client):
    r = client.post("/checker/dns-latency", json={
        "providers": [{"name": "1.1.1.1", "address": "1.1.1.1"}],
        "timeout": 2, "concurrency": 2,
    })
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_checker_protocols(client):
    r = client.get("/checker/protocols")
    assert r.status_code == 200
    assert "summaries" in r.json()


def test_checker_vless_modify(client):
    r = client.post("/checker/vless-modify", json={
        "configs": VLESS_A, "ips": "1.1.1.1\n2.2.2.2", "parse_ips": True,
    })
    assert r.status_code == 200
    body = r.json()
    assert body.get("error") is None
    assert body["total_generated"] == 2
    assert body["configs"][0].startswith("vless://550e8400-e29b-41d4-a716-446655440000@1.1.1.1:443")


def test_checker_netlify_generate(client):
    r = client.post("/checker/netlify-generate", json={
        "uuid": "550e8400-e29b-41d4-a716-446655440000", "path": "/ws",
        "netlify_domain": "app.netlify.com", "xhttp_object": "warp",
        "snis": ["a.com", "b.com"], "ips": ["1.1.1.1", "2.2.2.2"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["total_generated"] == 4


def test_checker_netlify_generate_missing_fields(client):
    r = client.post("/checker/netlify-generate", json={
        "uuid": "", "path": "", "netlify_domain": "", "xhttp_object": "",
        "snis": [], "ips": [],
    })
    assert r.status_code == 400


def test_checker_xray_scan_requires_xray(client):
    r = client.post("/checker/xray-scan", json={
        "ip_input": "1.1.1.1", "config_json": "{}",
    })
    assert r.status_code in (200, 400)