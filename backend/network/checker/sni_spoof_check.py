"""SNI Spoof Check (Network Checker).

Ported from the upstream sni_spoof_check_service.dart (GPL-3.0
mirarr-app/network-checker). This is a reachability diagnostic: it resolves a
target, probes its IPs on the configured ports, and — when IP verification is
enabled — confirms the target's Cloudflare front resolves to the same public IP
by reading the `/cdn-cgi/trace` endpoint over a direct TLS connection that
presents the target as the SNI hostname.

Security note: this is a passive connectivity/accessibility check against the
target itself (mirroring the upstream tool). It performs no MITM, no credential
harvesting and no spoofing of traffic meant for other parties.
"""

from __future__ import annotations

import re
import socket
import ssl
import time

import httpx

from ...network.diagnostics import public_ip as _jpnh_public_ip
from . import common

DEFAULT_TARGETS = """hcaptcha.com
www.sciencedirect.com
auth.vercel.com
chess.com
unpkg.com
static.cloudflareinsights.com
www.speedtest.net"""

DEFAULT_PORTS = [443]
ALL_PORTS = [443, 2053, 2083, 2087, 2096, 8443]

_PUBLIC_IP_API_URL = "http://chabokan.net/ip/"
_IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


class SniCheckConfig:
    def __init__(self, ports: list[int] | None = None, timeout: float = 5.0,
                 retries: int = 3, concurrency: int = 20,
                 enable_ip_check: bool = True, manual_ip: str = ""):
        self.ports = list(ports) if ports else list(DEFAULT_PORTS)
        self.timeout = timeout
        self.retries = retries
        self.concurrency = concurrency
        self.enable_ip_check = enable_ip_check
        self.manual_ip = manual_ip


def parse_targets(text: str) -> list[str]:
    """Parse targets (one per line, '#' starts a comment)."""
    return [
        line.strip() for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def is_ip_address(target: str) -> bool:
    return bool(_IPV4_RE.match(target))


def resolve_target(target: str) -> list[str]:
    """Resolve a domain to its IPv4 A records; IPs are returned as-is."""
    if is_ip_address(target):
        return [target]
    try:
        infos = socket.getaddrinfo(target, None, socket.AF_INET, socket.SOCK_STREAM)
        return sorted({info[4][0] for info in infos})
    except OSError:
        return []


def check_port(ip: str, port: int, timeout: float, retries: int) -> bool:
    """TCP reachability with retries (upstream checkPort)."""
    for _ in range(max(1, retries)):
        if common.tcp_connect(ip, port, timeout)["reachable"]:
            return True
    return False


def _fetch_public_ip() -> str | None:
    """Detect the user's public IP. Mirrors the upstream endpoint with a local
    fallback to the existing JPNH public-IP check."""
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True, trust_env=False) as client:
            resp = client.get(_PUBLIC_IP_API_URL)
        match = re.search(r'"ip"\s*:\s*"([^"]+)"', resp.text)
        if match:
            return match.group(1)
    except (httpx.HTTPError, OSError):
        pass
    try:
        result = _jpnh_public_ip(timeout=6.0)
        if result.get("status") == "ok" and result.get("ip"):
            return result["ip"]
    except Exception:  # noqa: BLE001 - fall through to None, like upstream
        pass
    return None


def _trace_ip_check(domain: str, ip: str, user_public_ip: str, timeout: float = 10.0) -> dict:
    """Hit https://{domain}/cdn-cgi/trace through a direct TLS connection to
    ip:443 presenting `domain` as the SNI hostname. Returns the `ip=` field."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    tls = None
    try:
        sock.connect((ip, 443))
        tls = context.wrap_socket(sock, server_hostname=domain)
        tls.settimeout(timeout)
        tls.sendall(f"GET /cdn-cgi/trace HTTP/1.1\r\nHost: {domain}\r\n"
                    "Connection: close\r\n\r\n".encode())
        response = b""
        while True:
            try:
                chunk = tls.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            response += chunk
            if len(response) > 8192:
                break
        text = response.decode("latin-1", errors="replace")
        match = re.search(r"^ip=(.+)$", text, re.MULTILINE)
        if not match:
            return {"matched": False, "detected_ip": None}
        detected = match.group(1).strip()
        return {"matched": detected == user_public_ip, "detected_ip": detected}
    except (socket.timeout, ssl.SSLError, OSError):
        return {"matched": False, "detected_ip": None}
    finally:
        try:
            if tls is not None:
                tls.close()
        except OSError:
            pass
        try:
            if tls is None:
                sock.close()
        except OSError:
            pass


def _scan_target(target: str, config: SniCheckConfig, user_public_ip: str | None) -> list[dict]:
    ips = resolve_target(target)
    if not ips:
        return [{"target": target, "ip": "", "status": "error",
                 "error": "Could not resolve", "port_results": [], "ip_check": None}]

    results: list[dict] = []
    for ip in ips:
        if ip.startswith("10.") or common.is_private_or_reserved_ipv4(ip):
            results.append({"target": target, "ip": ip, "status": "filtered",
                            "port_results": [], "ip_check": None})
            continue
        port_results = []
        open_count = 0
        for port in config.ports:
            open_port = check_port(ip, port, config.timeout, config.retries)
            port_results.append({"port": port, "is_open": open_port})
            if open_port:
                open_count += 1
        if open_count > 0:
            ip_check = None
            if (config.enable_ip_check and user_public_ip
                    and not is_ip_address(target)):
                ip_check = _trace_ip_check(target, ip, user_public_ip, config.timeout * 2)
            results.append({"target": target, "ip": ip, "status": "ok",
                            "port_results": port_results, "ip_check": ip_check})
        else:
            results.append({"target": target, "ip": ip, "status": "fail",
                            "port_results": port_results, "ip_check": None})
    return results


def sni_spoof_check(targets_text: str | None = None,
                    ports: list[int] | None = None,
                    timeout: float = 5.0,
                    retries: int = 3,
                    concurrency: int = 20,
                    enable_ip_check: bool = True,
                    manual_ip: str = "") -> dict:
    """Run the full SNI spoof check scan."""
    config = SniCheckConfig(ports=ports, timeout=timeout, retries=retries,
                            concurrency=concurrency, enable_ip_check=enable_ip_check,
                            manual_ip=manual_ip)
    targets = parse_targets(targets_text) if targets_text else parse_targets(DEFAULT_TARGETS)
    if not targets:
        return {"total": 0, "results": [], "ok": 0, "fail": 0, "filtered": 0,
                "error": 0, "user_public_ip": None, "error_message": "No targets provided"}

    user_public_ip: str | None = None
    if config.enable_ip_check:
        user_public_ip = config.manual_ip.strip() or _fetch_public_ip()

    results: list[dict] = []
    for batch in range(0, len(targets), concurrency):
        batch_targets = targets[batch:batch + concurrency]
        for sub in common.batched_executor(
                batch_targets, lambda t: _scan_target(t, config, user_public_ip),
                concurrency):
            results.extend(sub)

    counts = {"ok": 0, "fail": 0, "filtered": 0, "error": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {
        "total": len(targets),
        "results": results,
        "user_public_ip": user_public_ip,
        "ports": config.ports,
        "timeout": config.timeout,
        "retries": config.retries,
        **counts,
    }


def format_result_line(result: dict) -> str:
    tag = f"[{result['status'].upper()}]"
    if result["status"] == "error":
        return f"{tag} {result['target']} ({result.get('error') or 'Could not resolve'})"
    if result["status"] == "filtered":
        return f"{tag} {result['target']} -> {result['ip']} (Blocked/Internal IP)"
    port_str = " ".join(
        f"{p['port']}{'OK' if p['is_open'] else 'NO'}" for p in result["port_results"])
    line = f"{tag} {result['target']} -> {result['ip']} -> {port_str}"
    ip_check = result.get("ip_check")
    if ip_check:
        if ip_check.get("matched"):
            line += " IP-OK"
        elif ip_check.get("detected_ip"):
            line += f" IP-DIFF({ip_check['detected_ip']})"
        else:
            line += " IP-NONE"
    return line


def generate_report(data: dict) -> str:
    lines = ["=== SNI Spoof Check Report ===",
             f"Ports: {','.join(str(p) for p in data.get('ports', []))}",
             f"Timeout: {data.get('timeout')}s | Retries: {data.get('retries')}",
             f"Timestamp: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
             "---------------------------------------------------"]
    for status, label in (("ok", "OK (at least one open port)"),
                          ("fail", "FAIL (all ports closed)"),
                          ("error", "RESOLVE FAILED"),
                          ("filtered", "FILTERED (Blocked/IP 10.x)")):
        entries = [r for r in data.get("results", []) if r["status"] == status]
        if entries:
            lines.append("")
            lines.append(f"=== {label} [{len(entries)}] ===")
            lines.extend(format_result_line(r) for r in entries)
    lines.append("---------------------------------------------------")
    lines.append(f"Scan completed at {time.strftime('%Y-%m-%dT%H:%M:%S')}")
    return "\n".join(lines)