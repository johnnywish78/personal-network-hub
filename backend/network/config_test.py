"""End-to-end configuration test pipeline.

Pipeline: Parse -> Validate -> DNS -> TCP -> TLS -> protocol-specific check
-> final status.

Crucially, a config is never labeled WORKING purely because a TCP port is
open. Final status decisions:

  * PASS     all stages pass (validation + reachability + TLS where TLS is set)
  * PARTIAL  reachable but TLS or protocol-specific expectation failed
  * TIMEOUT  a stage timed out
  * FAIL     validation failed or address unreachable
"""

from __future__ import annotations

# This module is a runtime library, not a pytest test file. pytest globs
# ``*_test.py`` and would collect ``run_config_test`` as a test (its first
# argument is a config object, not a fixture) and warn on the imported
# ``TestResult`` enum. Mark it as a non-test module explicitly.
__test__ = False

import datetime
import time
from typing import Optional

from ..configs.model import ConfigStatus, NormalizedConfig, TestResult
from ..configs.validator import validate
from . import dns as dns_mod
from . import tcp as tcp_mod


def _stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _needs_tls(cfg: NormalizedConfig) -> bool:
    return str(cfg.security or "").lower() in ("tls", "reality")


def run_config_test(cfg: NormalizedConfig, timeout: float = 5.0) -> dict:
    """Run the full pipeline against one config.

    Returns a dict with per-stage results plus `result` and `status`.
    """
    started = time.monotonic()
    stages: dict = {}

    # 1. Validate
    validation = validate(cfg)
    stages["validation"] = validation
    if not validation["valid"]:
        return _final(cfg, TestResult.FAIL, stages, "validation failed: " + "; ".join(validation["errors"]), started)

    address = cfg.address or ""
    port = int(cfg.port or 0)

    # 2. DNS
    dns_result = dns_mod.query_host(address)
    stages["dns"] = dns_result
    if dns_result.get("status") == "timeout":
        return _final(cfg, TestResult.TIMEOUT, stages, "DNS lookup timed out", started)
    if not dns_result.get("ips"):
        return _final(cfg, TestResult.FAIL, stages, dns_result.get("error") or "DNS failed", started)

    # 3. TCP
    tcp_result = tcp_mod.tcp_check(address, port, timeout)
    stages["tcp"] = tcp_result
    if not tcp_result["reachable"]:
        if tcp_result.get("error") == "timeout":
            return _final(cfg, TestResult.TIMEOUT, stages, f"TCP connect to {address}:{port} timed out", started)
        return _final(cfg, TestResult.FAIL, stages, tcp_result.get("error") or f"TCP {address}:{port} unreachable", started)

    # 4. TLS when expected
    if _needs_tls(cfg):
        tls_result = tcp_mod.tls_check(address, port, sni=cfg.sni or cfg.address, timeout=timeout)
        stages["tls"] = tls_result
        if not tls_result["tls_ok"]:
            return _final(cfg, TestResult.PARTIAL, stages, tls_result.get("error") or "TLS handshake failed",
                          started, latency_ms=tcp_result.get("latency_ms"))
    else:
        stages["tls"] = {"skipped": True, "reason": "security not set to TLS/reality"}

    # 5. Protocol-specific checks
    proto_check = _protocol_specific(cfg, stages)
    stages["protocol"] = proto_check
    if proto_check.get("error"):
        return _final(cfg, TestResult.PARTIAL, stages, proto_check["error"], started,
                      latency_ms=tcp_result.get("latency_ms"))

    elapsed = round((time.monotonic() - started) * 1000, 1)
    return _final(cfg, TestResult.PASS, stages, None, started, latency_ms=elapsed,
                  reachability_ms=tcp_result.get("latency_ms"))


def _protocol_specific(cfg: NormalizedConfig, stages: dict) -> dict:
    """Checks that go beyond reachability for specific protocols."""
    # For full protocol validation we would need a real Xray client;
    # here we do lightweight structural checks that do not over-claim.
    if cfg.protocol == "vless":
        if not cfg.uuid:
            return {"ok": False, "error": "VLESS missing UUID"}
        return {"ok": True, "note": "VLESS UUID present; end-to-end requires client"}
    if cfg.protocol == "trojan":
        if not cfg.password:
            return {"ok": False, "error": "Trojan missing password"}
        return {"ok": True, "note": "Trojan password present; end-to-end requires client"}
    return {"ok": True, "note": "no extra protocol check defined"}


def _final(cfg: NormalizedConfig, result: TestResult, stages: dict, error: Optional[str],
           started: float, latency_ms: Optional[float] = None, reachability_ms: Optional[float] = None) -> dict:
    elapsed = round((time.monotonic() - started) * 1000, 1)
    status = {
        TestResult.PASS: ConfigStatus.WORKING,
        TestResult.PARTIAL: ConfigStatus.DEGRADED,
        TestResult.TIMEOUT: ConfigStatus.FAILED,
        TestResult.FAIL: ConfigStatus.FAILED,
    }[result]
    return {
        "config_id": cfg.id,
        "result": result.value,
        "status": status.value,
        "latency_ms": latency_ms or reachability_ms,
        "error": error,
        "timestamp": _stamp(),
        "duration_ms": elapsed,
        "stages": stages,
    }


def summarize(results: list[dict]) -> dict:
    counts = {"PASS": 0, "PARTIAL": 0, "TIMEOUT": 0, "FAIL": 0}
    for r in results:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    return {"total": len(results), "counts": counts}
