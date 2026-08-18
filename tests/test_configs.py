"""Normalizer, validator, storage, exporter tests."""

import pytest

from backend.configs import parser, exporter
from backend.configs.model import ConfigStatus
from backend.configs.normalizer import normalize, to_uri
from backend.configs.storage import ConfigStore
from backend.configs.validator import validate
from backend.storage.json_store import JsonStore

VLESS_URI = ("vless://550e8400-e29b-41d4-a716-446655440000@example.com:443"
             "?security=tls&sni=panel.example.com&type=xhttp&host=cdn.example.com"
             "&path=/data&mode=cors#RVG-Johnny")


def _cfg():
    return normalize(parser.parse_single(VLESS_URI), provider="RVG")


def test_normalize_preserves_raw():
    cfg = _cfg()
    assert cfg.raw_config == VLESS_URI
    assert cfg.protocol == "vless"
    assert cfg.provider == "RVG"
    assert cfg.address == "example.com"
    assert cfg.port == 443
    assert cfg.uuid == "550e8400-e29b-41d4-a716-446655440000"
    assert cfg.security == "tls"
    assert cfg.network == "xhttp"
    assert cfg.mode == "cors"
    assert cfg.status == ConfigStatus.UNKNOWN


def test_validate_valid_vless():
    result = validate(_cfg())
    assert result["valid"] is True


def test_validate_missing_fields():
    from backend.configs.model import NormalizedConfig
    bad = NormalizedConfig()
    result = validate(bad)
    assert result["valid"] is False
    assert any("address" in e for e in result["errors"])
    assert any("port" in e for e in result["errors"])


def test_validate_bad_port():
    from backend.configs.model import NormalizedConfig
    cfg = NormalizedConfig(address="1.1.1.1", port=99999, protocol="vless",
                           uuid="550e8400-e29b-41d4-a716-446655440000")
    result = validate(cfg)
    assert result["valid"] is False


def test_is_domain():
    from backend.configs.validator import is_domain, is_ip
    assert is_domain("example.com")
    assert is_domain("sub.sub.example.co.uk")
    assert not is_domain("not a domain")
    assert is_ip("1.1.1.1")
    assert not is_ip("999.999.999.999")


def test_storage_roundtrip(tmp_path):
    store = ConfigStore(JsonStore(tmp_path / "configs.json", []))
    cfg = _cfg()
    store.save(cfg)
    assert store.get(cfg.id) is not None
    assert store.list()[0].uuid == cfg.uuid

    store.update_status(cfg.id, ConfigStatus.WORKING, latency_ms=42.5)
    updated = store.get(cfg.id)
    assert updated.status == ConfigStatus.WORKING
    assert updated.latency_ms == 42.5
    assert updated.last_tested_at is not None

    assert store.delete(cfg.id) is True
    assert store.get(cfg.id) is None
    assert store.delete(cfg.id) is False


def test_storage_counts(tmp_path):
    store = ConfigStore(JsonStore(tmp_path / "c.json", []))
    c1 = _cfg()
    c2 = normalize(parser.parse_single(VLESS_URI.replace("#RVG-Johnny", "#Two")), provider="RVG")
    store.save(c1)
    store.save(c2)
    store.update_status(c1.id, ConfigStatus.WORKING)
    store.update_status(c2.id, ConfigStatus.FAILED)
    counts = store.counts()
    assert counts["total"] == 2
    assert counts["working"] == 1
    assert counts["failed"] == 1


def test_exporter_uris_preserves_original():
    cfg = _cfg()
    out = exporter.export_uris([cfg])
    assert VLESS_URI in out


def test_exporter_json_omits_private_key():
    cfg = _cfg()
    out = exporter.export_json([cfg])
    import json as jsonlib
    data = jsonlib.loads(out)
    assert "private_key" not in data[0]


def test_exporter_xray_vless():
    cfg = _cfg()
    out = exporter.export_xray_config(cfg)
    import json as jsonlib
    xray = jsonlib.loads(out)
    assert xray["outbounds"][0]["protocol"] == "vless"
    assert xray["outbounds"][0]["streamSettings"]["network"] == "xhttp"


def test_to_uri_rebuild():
    cfg = _cfg()
    uri = to_uri(cfg)
    assert uri.startswith("vless://")
    assert "example.com" in uri


def test_normalize_ignores_no_raw():
    parsed = {"protocol": "trojan", "password": "x", "address": "a.com", "port": 443}
    cfg = normalize(parsed)
    assert cfg.raw_config == ""
    assert cfg.protocol == "trojan"
