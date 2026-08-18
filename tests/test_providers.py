"""Provider adapters, Xray detection, client detection, vault, logging tests."""

from backend.configs import parser
from backend.providers.registry import build_registry
from backend.providers.rvg.adapter import RvgAdapter
from backend.services.client_detector import detect_clients
from backend.services.logging import LogHub, redact
from backend.storage.json_store import JsonStore
from backend.storage.vault import SecretVault
from backend.xray.manager import XrayManager

VLESS_URI = ("vless://550e8400-e29b-41d4-a716-446655440000@example.com:443"
             "?security=tls&sni=panel.example.com&type=xhttp&host=cdn.example.com"
             "&path=/data&mode=cors#RVG-Johnny")


def test_registry_contains_providers():
    registry = build_registry()
    names = registry.names()
    assert "bpb-worker-panel" in names
    assert "bpb-wizard" in names
    assert "zeus" in names
    assert "rvg" in names
    assert "aether" in names
    assert "nova" in names


def test_provider_describe_includes_metadata():
    registry = build_registry()
    for adapter in registry.all():
        desc = adapter.describe()
        assert desc["name"] == adapter.name
        assert "capabilities" in desc or adapter.integration_type == "launcher"


def test_bpb_panel_configure_and_open():
    registry = build_registry()
    bpb = registry.get("bpb-worker-panel")
    assert bpb.supports_action("open")
    result = bpb.set_panel_url("https://panel.example.workers.dev")
    assert result["ok"] is True
    opened = bpb.open()
    assert opened["ok"] is True
    assert opened["url"] == "https://panel.example.workers.dev"


def test_bpb_import_configs():
    registry = build_registry()
    bpb = registry.get("bpb-worker-panel")
    parsed = bpb.import_config(VLESS_URI + "\n" + "trojan://pw@host:443#t")
    assert len(parsed) == 2


def test_zeus_default_open_fails_without_url():
    registry = build_registry()
    zeus = registry.get("zeus")
    result = zeus.open()
    assert result["ok"] is False


def test_rvg_parse_vless_parameters():
    rvg = RvgAdapter()
    r = rvg.parse_config(VLESS_URI)
    assert r["ok"] is True
    params = r["parameters"]
    assert params["protocol"] == "vless"
    assert params["address"] == "example.com"
    assert params["security"] == "tls"
    assert params["network"] == "xhttp"
    assert params["mode"] == "cors"
    assert params["sni"] == "panel.example.com"


def test_rvg_qr_generation():
    rvg = RvgAdapter()
    b64 = rvg.to_qr_base64(VLESS_URI)
    assert b64 and len(b64) > 100


def test_aether_detection_never_crashes():
    registry = build_registry()
    aether = registry.get("aether")
    result = aether.detect()
    assert "found" in result
    assert "path" in result


def test_xray_detection_graceful():
    mgr = XrayManager(binary="/nonexistent/xray")
    status = mgr.status()
    assert status["installed"] is False


def test_xray_validate_missing_file():
    mgr = XrayManager(binary="/nonexistent/xray")
    r = mgr.validate_config("/nonexistent/config.json")
    assert r["valid"] is False
    assert r["error"]


def test_client_detection_returns_three():
    results = detect_clients()
    assert len(results) == 3
    for r in results:
        assert r["id"] in ("v2rayN", "hiddify", "v2box")
        assert "detected" in r


def test_vault_roundtrip(tmp_path):
    vault = SecretVault(path=tmp_path / "secrets.json")
    vault.set("github_token", "ghp_supersecret123")
    assert vault.get("github_token") == "ghp_supersecret123"
    masked = vault.masked()
    assert masked["github_token"] != "ghp_supersecret123"
    vault.delete("github_token")
    assert vault.has("github_token") is False


def test_log_hub_redacts_secrets(tmp_path):
    store = JsonStore(tmp_path / "logs.json", [])
    loghub = LogHub(store)
    loghub.error("configs", f"import failed for {VLESS_URI}")
    entries = loghub.entries()
    assert entries[0]["level"] == "ERROR"
    assert "REDACTED" in entries[0]["message"]
    assert "550e8400-e29b-41d4-a716-446655440000" not in entries[0]["message"]


def test_redact_helper():
    assert "REDACTED" in redact(VLESS_URI)
    assert "REDACTED" in redact("trojan://pw@host:443")
