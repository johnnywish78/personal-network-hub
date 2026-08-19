"""Network diagnostics tests (offline-safe where possible, real network optional)."""

import socket

from backend.network import dns, latency, tcp
from backend.network.config_test import run_config_test
from backend.configs import parser
from backend.configs.normalizer import normalize


def test_dns_query_system():
    r = dns.query_host("localhost")
    assert r["host"] == "localhost"
    assert r["status"] in ("ok", "error")
    if r["status"] == "ok":
        assert "127.0.0.1" in r["ips"]


def test_dns_query_resolver_timeout():
    # Reserved/testing IP that will not answer DNS quickly -> expect timeout/error, not a crash.
    r = dns.query_host("example.com", resolver="192.0.2.1", timeout=0.3)
    assert r["status"] in ("ok", "timeout", "error")


def test_tcp_check_localhost_open():
    # Start a throwaway listener and confirm reachability detection.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        r = tcp.tcp_check("127.0.0.1", port, timeout=1.0)
        assert r["reachable"] is True
        assert r["latency_ms"] is not None
    finally:
        srv.close()


def test_tcp_check_closed_port():
    r = tcp.tcp_check("127.0.0.1", 1, timeout=1.0)  # port 1 almost certainly closed
    assert r["reachable"] is False


def test_tls_check_fails_on_plain_tcp():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        r = tcp.tls_check("127.0.0.1", port, timeout=1.0)
        assert r["tls_ok"] is False
    finally:
        srv.close()


def test_ping_tcp_fallback():
    r = latency.ping("127.0.0.1", count=1, port=1, timeout=0.5)
    assert r["status"] in ("ok", "error")


def test_config_test_unreachable_domain():
    cfg = normalize(parser.parse_single(
        "vless://550e8400-e29b-41d4-a716-446655440000@nonexistent.invalid:443"), provider="test")
    result = run_config_test(cfg, timeout=1.0)
    assert result["result"] in ("FAIL", "TIMEOUT")
    assert result["status"] == "FAILED"
    assert "dns" in result["stages"]


def test_config_test_missing_fields():
    from backend.configs.model import NormalizedConfig
    cfg = NormalizedConfig()
    result = run_config_test(cfg)
    assert result["result"] == "FAIL"
    assert "validation" in result["stages"]
