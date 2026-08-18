"""General internet and network diagnostics.

Every test returns: status, latency, error, timestamp.
"""

from __future__ import annotations

import datetime
import json
import time
from typing import Optional

import httpx

from . import dns as dns_mod
from . import latency as latency_mod
from . import tcp as tcp_mod


def _stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _make_result(status: str, latency_ms: Optional[float] = None, error: Optional[str] = None, **extra) -> dict:
    return {"status": status, "latency_ms": latency_ms, "error": error, "timestamp": _stamp(), **extra}


def internet_check(timeout: float = 6.0) -> dict:
    """Basic connectivity check via an HTTPS request to a known host."""
    start = time.monotonic()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
            resp = client.get("https://www.cloudflare.com/cdn-cgi/trace")
        elapsed = round((time.monotonic() - start) * 1000, 1)
        if resp.status_code == 200 and "ip=" in resp.text:
            ip = None
            for line in resp.text.splitlines():
                if line.startswith("ip="):
                    ip = line.split("=", 1)[1]
                    break
            return _make_result("online", elapsed, ip=ip)
        return _make_result("online", elapsed, ip=None)
    except httpx.HTTPError as exc:
        return _make_result("offline", error=f"http error: {exc.__class__.__name__}")
    except OSError as exc:
        return _make_result("offline", error=str(exc))


def public_ip(timeout: float = 6.0) -> dict:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, trust_env=False) as client:
            resp = client.get("https://www.cloudflare.com/cdn-cgi/trace")
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                if line.startswith("ip="):
                    return _make_result("ok", ip=line.split("=", 1)[1])
        return _make_result("error", error="could not extract IP")
    except httpx.HTTPError as exc:
        return _make_result("error", error=f"http error: {exc.__class__.__name__}")


def domain_check(host: str, port: Optional[int] = None, timeout: float = 5.0) -> dict:
    """DNS + TCP + TLS for a domain (TLS only when port is 443/8443)."""
    dns_result = dns_mod.query_host(host)
    if not dns_result.get("ips"):
        return _make_result("fail", error=dns_result.get("status"), dns=dns_result)
    target_port = port or 443
    tcp_result = tcp_mod.tcp_check(host, target_port, timeout)
    result: dict = _make_result("ok" if tcp_result["reachable"] else "fail",
                                latency_ms=tcp_result.get("latency_ms"),
                                error=tcp_result.get("error"), dns=dns_result, tcp=tcp_result)
    if tcp_result["reachable"] and target_port in (443, 8443, 2053, 2083, 2096):
        tls_result = tcp_mod.tls_check(host, target_port, timeout=timeout)
        result["tls"] = tls_result
        result["latency_ms"] = tls_result.get("latency_ms") or result.get("latency_ms")
        if not tls_result["tls_ok"]:
            result["status"] = "partial"
            result["error"] = tls_result.get("error")
    return result


def run_network_lab() -> dict:
    """Runs the set of standard network-lab diagnostics."""
    return {
        "internet": internet_check(),
        "public_ip": public_ip(),
        "dns_cloudflare": dns_mod.query_host("cloudflare.com", "1.1.1.1"),
        "dns_google": dns_mod.query_host("google.com", "8.8.8.8"),
        "latency_1_1_1_1": latency_mod.ping("1.1.1.1", count=3),
        "latency_8_8_8_8": latency_mod.ping("8.8.8.8", count=3),
        "github": domain_check("github.com", 443),
        "cloudflare_com": domain_check("cloudflare.com", 443),
    }


def clean_ip_test(address: str, ports: Optional[list[int]] = None, timeout: float = 3.0) -> list[dict]:
    """Test a set of common proxy ports against an address (clean-IP style)."""
    ports = ports or [443, 8443, 2053, 2083, 2086, 2087, 2096, 80]
    results = []
    for port in ports:
        results.append(tcp_mod.tcp_check(address, port, timeout))
    return results


def latency_matrix() -> dict:
    """Compact latency summary for dashboard."""
    out = {}
    for host in ["1.1.1.1", "8.8.8.8", "9.9.9.9"]:
        out[host] = latency_mod.ping(host, count=3)
    return out
