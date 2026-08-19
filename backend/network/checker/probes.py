"""Domain checker and DNS latency test (Network Checker probes).

Ported from upstream connectivity_service.dart and dns_latency_service.dart.
"""

from __future__ import annotations

import time

import httpx

from . import common
from .data import dns_providers as _dns_providers
from .data import top_domains as _top_domains

DEFAULT_TIMEOUT = 3.0
DEFAULT_CONCURRENCY = 10


def _build_uri(target: str) -> str:
    url = target.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"
    return url


def check_domain(target: str, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """HTTP HEAD reachability for a single target (upstream checkSingle)."""
    uri = _build_uri(target)
    start = time.monotonic()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.head(uri)
        elapsed = round((time.monotonic() - start) * 1000, 1)
        return {
            "target": target,
            "success": response.status_code < 400,
            "response_time_ms": elapsed,
            "status_code": response.status_code,
            "error": None,
        }
    except httpx.TimeoutException:
        elapsed = round((time.monotonic() - start) * 1000, 1)
        return {"target": target, "success": False, "response_time_ms": elapsed,
                "status_code": None, "error": f"Connection timed out after {timeout}s"}
    except Exception as exc:  # noqa: BLE001 - report gracefully, like upstream
        elapsed = round((time.monotonic() - start) * 1000, 1)
        return {"target": target, "success": False, "response_time_ms": elapsed,
                "status_code": None, "error": _format_error(exc)}


def check_domains(targets: list[str], timeout: float = DEFAULT_TIMEOUT,
                  concurrency: int = DEFAULT_CONCURRENCY) -> list[dict]:
    if not targets:
        return []
    return common.batched_executor(targets, lambda t: check_domain(t, timeout), concurrency)


def _format_error(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    if "no route to host" in lowered:
        return "No route to host"
    if "connection refused" in lowered:
        return "Connection refused"
    if "network is unreachable" in lowered:
        return "Network unreachable"
    if "ssl" in lowered or "handshake" in lowered:
        return "SSL/TLS handshake failed"
    if "certificate" in lowered:
        return "Invalid certificate"
    if len(message) > 100:
        return message[:97] + "..."
    return message


def dns_latency_single(address: str, provider_name: str, timeout: float = 2.0) -> dict:
    """UDP DNS latency to a provider (upstream checkSingle: google.com A query)."""
    result = common.udp_dns_query(address, "google.com", timeout)
    return {
        "address": address,
        "provider_name": provider_name,
        "success": result["success"] and result["rcode"] == 0,
        "latency_ms": result["latency_ms"],
        "error": result["error"],
    }


def dns_latency_multi(providers: list[dict] | None = None,
                      timeout: float = 2.0,
                      concurrency: int = 10) -> list[dict]:
    """Test latency to all provider addresses (upstream checkMultiple)."""
    providers = providers if providers is not None else _dns_providers()
    targets = [
        (address, provider.get("name", address))
        for provider in providers
        for address in provider.get("addresses", [])
    ]
    results = common.batched_executor(
        targets,
        lambda pair: dns_latency_single(pair[0], pair[1], timeout),
        concurrency,
    )
    results.sort(key=lambda r: r["latency_ms"] if r["latency_ms"] is not None else float("inf"))
    return results


def default_domains() -> list[str]:
    return list(_top_domains())


def default_providers() -> list[dict]:
    return list(_dns_providers())