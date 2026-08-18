"""IP scanners: DNS Hunter, Edge IP Checker, Akamai scanner.

Ported from upstream dns_hunter_service.dart, edge_ip_scanner.dart and
akamai_ip_scanner.dart.
"""

from __future__ import annotations

import re
import ssl
import socket
import time
from typing import Optional

from . import common
from .data import akamai_ip_ranges as _akamai_ranges
from .data import edge_ip_ranges as _edge_ranges

DNS_HUNTER_DEFAULT_TIMEOUT = 2.0
DNS_HUNTER_DEFAULT_CONCURRENCY = 50

_TWITTER_PATTERNS = [
    r"^104\.(1[6-9]|2[0-3])\.",
    r"^172\.(6[4-9]|7[0-1])\.",
    r"^108\.162\.",
    r"^162\.15[8-9]\.",
]
_YOUTUBE_PATTERNS = [
    r"^142\.25[0-1]\.",
    r"^172\.217\.",
    r"^172\.253\.",
    r"^74\.125\.",
    r"^208\.117\.",
]


class _DnsHunterTarget:
    def __init__(self, name: str, domain: str, patterns: list[str]):
        self.name = name
        self.domain = domain
        self.patterns = [re.compile(p) for p in patterns]

    def matches(self, ip: str) -> bool:
        if not self.patterns:
            return True
        return any(pattern.match(ip) for pattern in self.patterns)


def _dns_hunter_target(name: str, custom_domain: str = "") -> _DnsHunterTarget:
    if name == "youtube":
        return _DnsHunterTarget("YouTube", "youtube.com", _YOUTUBE_PATTERNS)
    if name == "custom":
        return _DnsHunterTarget("Custom", custom_domain.strip(), [])
    return _DnsHunterTarget("X / Twitter", "x.com", _TWITTER_PATTERNS)


def _test_dns_hunter_ip(ip: str, target: _DnsHunterTarget, timeout: float) -> dict:
    result = common.udp_dns_query(ip, target.domain, timeout)
    if not result["success"]:
        return {"ip": ip, "is_clean": False, "latency_ms": result["latency_ms"],
                "resolved_ips": [], "error": result["error"] or "No valid response",
                "supports_secure_dns": False}
    public_ips = [
        resolved for resolved in result["ips"]
        if resolved != ip and not common.is_private_or_reserved_ipv4(resolved)
    ]
    if not public_ips:
        return {"ip": ip, "is_clean": False, "latency_ms": result["latency_ms"],
                "resolved_ips": result["ips"], "error": "No valid response",
                "supports_secure_dns": False}
    is_clean = target.matches(public_ips[0]) or any(target.matches(p) for p in public_ips)
    return {"ip": ip, "is_clean": is_clean, "latency_ms": result["latency_ms"],
            "resolved_ips": public_ips, "error": None, "supports_secure_dns": False}


def _test_secure_dns(ip: str, timeout: float = 8.0) -> bool:
    result = common.tcp_connect(ip, 443, timeout)
    return result["reachable"]


def dns_hunter_scan(ranges: list[str],
                    target: str = "twitter",
                    custom_domain: str = "",
                    concurrency: int = DNS_HUNTER_DEFAULT_CONCURRENCY,
                    timeout: float = DNS_HUNTER_DEFAULT_TIMEOUT,
                    check_secure_dns: bool = False,
                    max_ips: int = 500) -> dict:
    """Scan DNS servers inside CIDR ranges for clean responses."""
    tgt = _dns_hunter_target(target, custom_domain)
    ips: list[str] = []
    for cidr in ranges:
        for ip in common.generate_ips_from_subnet(cidr):
            if len(ips) >= max_ips:
                break
            ips.append(ip)
        if len(ips) >= max_ips:
            break

    results = common.batched_executor(ips, lambda ip: _test_dns_hunter_ip(ip, tgt, timeout),
                                      concurrency)
    clean = [r for r in results if r["is_clean"]]
    if check_secure_dns and clean:
        secure = common.batched_executor(
            [r["ip"] for r in clean], lambda ip: _test_secure_dns(ip), concurrency)
        for result, supported in zip(clean, secure):
            result["supports_secure_dns"] = supported

    return {
        "target": tgt.name,
        "domain": tgt.domain,
        "scanned": len(ips),
        "clean": len(clean),
        "total_ranges": len(ranges),
        "results": results,
    }


# --- Edge IP Checker --------------------------------------------------------

class EdgeScanConfig:
    def __init__(self, test_domain: str = "chatgpt.com", test_path: str = "/",
                 port: int = 443, timeout: float = 3.0, max_workers: int = 20,
                 test_download: bool = True, download_size: int = 100 * 1024):
        self.test_domain = test_domain
        self.test_path = test_path
        self.port = port
        self.timeout = timeout
        self.max_workers = max_workers
        self.test_download = test_download
        self.download_size = download_size


def _split_ip_port(value: str, default_port: int) -> tuple[str, int]:
    if ":" in value:
        ip_part, _, port_part = value.rpartition(":")
        port = common._safe_int(port_part)  # noqa: SLF001
        if port is not None and 0 < port <= 65535 and common.is_valid_ipv4(ip_part):
            return ip_part, port
    return value, default_port


def _test_edge_ip_http(ip: str, config: EdgeScanConfig) -> Optional[dict]:
    target_ip, target_port = _split_ip_port(ip, config.port)
    start = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(config.timeout)
    try:
        sock.connect((target_ip, target_port))
    except (socket.timeout, OSError) as exc:
        sock.close()
        return {"ip": ip, "port": target_port, "success": False,
                "error": f"Connection failed: {_friendly(exc)}"}
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        tls = context.wrap_socket(sock, server_hostname=config.test_domain)
    except (ssl.SSLError, OSError) as exc:
        try:
            sock.close()
        except OSError:
            pass
        return {"ip": ip, "port": target_port, "success": False,
                "error": f"TLS handshake failed: {_friendly(exc)}"}

    try:
        request = (f"GET {config.test_path} HTTP/1.1\r\n"
                   f"Host: {config.test_domain}\r\n"
                   f"Connection: close\r\n\r\n").encode()
        tls.sendall(request)
        response = b""
        downloaded = 0
        tls.settimeout(config.timeout)
        while True:
            try:
                chunk = tls.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            response += chunk
            downloaded += len(chunk)
            if config.test_download and downloaded >= config.download_size:
                break
        latency = round((time.monotonic() - start) * 1000, 1)
        if b"HTTP/" in response[:20]:
            download_time = (time.monotonic() - start) / 1000.0
            speed_kbps = round((downloaded / 1024.0) / download_time, 1) if download_time > 0 else 0.0
            return {"ip": ip, "port": target_port, "success": True, "latency_ms": latency,
                    "speed_kbps": speed_kbps, "downloaded_bytes": downloaded, "error": None}
        return None
    except OSError as exc:
        return {"ip": ip, "port": target_port, "success": False,
                "error": f"Request failed: {_friendly(exc)}"}
    finally:
        try:
            tls.close()
        except OSError:
            pass


def _test_edge_ip_fast(ip: str, config: EdgeScanConfig) -> Optional[dict]:
    target_ip, target_port = _split_ip_port(ip, config.port)
    start = time.monotonic()
    result = _tls_connect_raw(target_ip, target_port, config.test_domain, config.timeout)
    if not result["reachable"]:
        return {"ip": ip, "port": target_port, "success": False,
                "error": result["error"]}
    latency = round((time.monotonic() - start) * 1000, 1)
    return {"ip": ip, "port": target_port, "success": True, "latency_ms": latency, "error": None}


def _tls_connect_raw(address: str, port: int, sni: str, timeout: float) -> dict:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((address, port))
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        tls = context.wrap_socket(sock, server_hostname=sni)
        tls.close()
        return {"reachable": True, "error": None}
    except (ssl.SSLError, OSError) as exc:
        try:
            sock.close()
        except OSError:
            pass
        return {"reachable": False, "error": f"TLS handshake failed: {_friendly(exc)}"}


def edge_ip_scan(ip_input: str | list[str], config: EdgeScanConfig | None = None) -> dict:
    config = config or EdgeScanConfig()
    ips = parse_ips(ip_input)
    test = _test_edge_ip_http if config.test_download else _test_edge_ip_fast
    results = [r for r in common.batched_executor(ips, lambda ip: test(ip, config),
                                                   config.max_workers) if r is not None]
    working = [r for r in results if r["success"]]
    return {
        "total": len(ips),
        "scanned": len(results),
        "successful": len(working),
        "working_ips": working,
        "results": results,
    }


# --- Akamai scanner ---------------------------------------------------------

class AkamaiScanConfig:
    def __init__(self, port: int = 443, timeout: float = 2.0, max_workers: int = 100):
        self.port = port
        self.timeout = timeout
        self.max_workers = max_workers


def _test_akamai_port(ip: str, config: AkamaiScanConfig) -> dict:
    result = common.tcp_connect(ip, config.port, config.timeout)
    return {"ip": ip, "port": config.port, "is_open": result["reachable"],
            "latency_ms": result["latency_ms"], "error": result["error"]}


def akamai_scan(ip_input: str | list[str], config: AkamaiScanConfig | None = None) -> dict:
    config = config or AkamaiScanConfig()
    ips = parse_ips(ip_input)
    results = common.batched_executor(ips, lambda ip: _test_akamai_port(ip, config),
                                      config.max_workers)
    open_ips = [r for r in results if r["is_open"]]
    return {"total": len(ips), "open": len(open_ips), "open_ips": open_ips, "results": results}


def parse_ips(ip_input: str | list[str]) -> list[str]:
    if isinstance(ip_input, list):
        text = "\n".join(ip_input)
    else:
        text = ip_input
    return common.parse_ip_input(text)


def _friendly(exc: BaseException) -> str:
    if isinstance(exc, socket.timeout):
        return "Connection timed out"
    return common._friendly_os_error(exc) if isinstance(exc, OSError) else str(exc)


def default_akamai_ranges() -> list[str]:
    return list(_akamai_ranges())


def default_edge_ranges() -> list[str]:
    return list(_edge_ranges())