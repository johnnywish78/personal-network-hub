"""CDN/Xray scanner (Network Checker).

Ported from upstream cdn_config_scanner.dart + xray_process_manager.dart.
Drives the system `xray` binary (found via backend/xray/detector.py) with a
modified copy of the user's config for each candidate IP, then probes the test
URL through the SOCKS5 inbound using curl (or a pure-Python SOCKS5 fallback).
"""

from __future__ import annotations

import json
import random
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from ...xray.detector import find_binary
from . import common

DEFAULT_TEST_URL = "https://www.google.com/generate_204"
DEFAULT_CONCURRENCY = 5
DEFAULT_TIMEOUT = 10.0
DEFAULT_STARTUP_DELAY = 2.0


class XrayUnavailableError(Exception):
    pass


def _parse_config(config_json: str) -> dict:
    try:
        config = json.loads(config_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    if not isinstance(config, dict) or "inbounds" not in config or "outbounds" not in config:
        raise ValueError('Config must contain "inbounds" and "outbounds" sections')
    return config


def extract_outbound_address(config: dict) -> Optional[str]:
    for outbound in config.get("outbounds", []):
        protocol = outbound.get("protocol")
        if protocol in ("vless", "vmess", "trojan"):
            vnext = (outbound.get("settings") or {}).get("vnext") or []
            if vnext:
                return vnext[0].get("address")
    return None


def _find_socks_inbound(config: dict) -> Optional[dict]:
    for inbound in config.get("inbounds", []):
        if inbound.get("protocol") in ("socks", "http"):
            return inbound
    return None


def _modified_config(config: dict, new_port: int, new_address: str) -> dict:
    modified = json.loads(json.dumps(config))
    for inbound in modified.get("inbounds", []):
        if inbound.get("protocol") in ("socks", "http"):
            inbound["port"] = new_port
            break
    for outbound in modified.get("outbounds", []):
        protocol = outbound.get("protocol")
        if protocol in ("vless", "vmess", "trojan"):
            vnext = (outbound.get("settings") or {}).get("vnext") or []
            if vnext:
                vnext[0]["address"] = new_address
            break
    return modified


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def _test_via_socks5(proxy_port: int, test_url: str, timeout: float) -> dict:
    """Probe test_url through a SOCKS5 proxy (curl if present, else pure Python)."""
    if shutil.which("curl"):
        return _test_via_curl(proxy_port, test_url, timeout)
    return _test_via_python_socks(proxy_port, test_url, timeout)


def _test_via_curl(proxy_port: int, test_url: str, timeout: float) -> dict:
    start = time.monotonic()
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code},%{time_total}",
             "--proxy", f"socks5h://127.0.0.1:{proxy_port}",
             "--connect-timeout", str(int(timeout)),
             "--max-time", str(int(timeout) + 2), "-k", test_url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            if len(parts) >= 2:
                try:
                    status = int(parts[0])
                except ValueError:
                    status = 0
                try:
                    time_ms = float(parts[1]) * 1000
                except ValueError:
                    time_ms = 0.0
                if 200 <= status < 300:
                    return {"success": True, "latency_ms": round(time_ms, 1), "error": None}
                return {"success": False, "latency_ms": round(time_ms, 1), "error": f"HTTP {status}"}
        stderr = result.stderr.strip()
        return {"success": False, "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "error": stderr or f"curl exit code {result.returncode}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "latency_ms": None, "error": "Connection timed out"}
    except OSError as exc:
        return {"success": False, "latency_ms": None, "error": str(exc)}


def _test_via_python_socks(proxy_port: int, test_url: str, timeout: float) -> dict:
    start = time.monotonic()
    try:
        from urllib.parse import urlparse
        parsed = urlparse(test_url)
        host = parsed.hostname or "www.google.com"
        port = parsed.port or 443
        path = parsed.path or "/"

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect(("127.0.0.1", proxy_port))
            sock.sendall(b"\x05\x01\x00")
            reply = sock.recv(2)
            if len(reply) != 2 or reply[0] != 0x05 or reply[1] != 0x00:
                return {"success": False, "latency_ms": None, "error": "SOCKS5 auth negotiation failed"}
            host_bytes = host.encode()
            request = bytes([0x05, 0x01, 0x00, 0x03, len(host_bytes)]) + host_bytes + \
                (port).to_bytes(2, "big")
            sock.sendall(request)
            response = sock.recv(10)
            if len(response) < 2 or response[1] != 0x00:
                return {"success": False, "latency_ms": None, "error": "SOCKS5 CONNECT failed"}

            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            tls = context.wrap_socket(sock, server_hostname=host)
            tls.settimeout(timeout)
            tls.sendall(f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
            data = tls.recv(4096)
            status_line = data.split(b"\r\n", 1)[0] if data else b""
            status = int(status_line.split(b" ", 2)[1]) if b" " in status_line else 0
            elapsed = round((time.monotonic() - start) * 1000, 1)
            if 200 <= status < 300:
                return {"success": True, "latency_ms": elapsed, "error": None}
            return {"success": False, "latency_ms": elapsed, "error": f"HTTP {status}"}
        finally:
            try:
                sock.close()
            except OSError:
                pass
    except (socket.timeout, OSError, ssl.SSLError) as exc:
        return {"success": False, "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "error": f"Proxy test failed: {common._friendly_os_error(exc) if isinstance(exc, OSError) else exc}"}


def _scan_single_ip(ip: str, config: dict, xray_binary: str, test_url: str,
                    timeout: float, startup_delay: float, temp_dir: Path) -> dict:
    instance: Optional[subprocess.Popen] = None
    config_path: Optional[Path] = None
    port = _free_port()
    try:
        modified = _modified_config(config, port, ip)
        suffix = f"{int(time.time() * 1000)}_{random.randint(0, 99999)}"
        config_path = temp_dir / f"config_{suffix}.json"
        config_path.write_text(json.dumps(modified), encoding="utf-8")
        instance = subprocess.Popen(
            [xray_binary, "-c", str(config_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(startup_delay)
        if instance.poll() is not None:
            return {"ip": ip, "success": False, "latency_ms": None,
                    "error": f"Xray process died (exit={instance.returncode})"}
        result = _test_via_socks5(port, test_url, timeout)
        return {"ip": ip, **result}
    except OSError as exc:
        return {"ip": ip, "success": False, "latency_ms": None,
                "error": f"Xray start failed: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"ip": ip, "success": False, "latency_ms": None, "error": str(exc)}
    finally:
        if instance is not None and instance.poll() is None:
            instance.terminate()
            try:
                instance.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                instance.kill()
                try:
                    instance.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
        if config_path is not None:
            try:
                config_path.unlink()
            except OSError:
                pass


def cdn_scan(ip_input: str | list[str], config_json: str,
             concurrency: int = DEFAULT_CONCURRENCY,
             timeout: float = DEFAULT_TIMEOUT,
             startup_delay: float = DEFAULT_STARTUP_DELAY,
             test_url: str = DEFAULT_TEST_URL,
             max_ips: int = 200) -> dict:
    """Scan candidate IPs through xray using the user's outbound config."""
    xray_binary = find_binary()
    if not xray_binary:
        raise XrayUnavailableError(
            "Xray binary not found. Install xray (or add it to PATH) to use the "
            "CDN/Xray scanner.")

    config = _parse_config(config_json)
    original_address = extract_outbound_address(config)
    if not original_address:
        raise ValueError("Config has no vless/vmess/trojan outbound with a server address.")

    ips = [line.strip() for line in ip_input.splitlines() if line.strip()] \
        if isinstance(ip_input, str) else list(ip_input)
    ips = common.parse_ip_input("\n".join(ips)) if ips else []
    if not ips:
        raise ValueError("No valid IPs provided.")

    with tempfile.TemporaryDirectory(prefix="jpnh-xray-") as tmp:
        temp_dir = Path(tmp)
        results = common.batched_executor(
            ips,
            lambda ip: _scan_single_ip(ip, config, xray_binary, test_url,
                                       timeout, startup_delay, temp_dir),
            concurrency,
        )
        results.sort(key=lambda r: r["latency_ms"] if r.get("latency_ms") is not None else float("inf"))

    successful = [r for r in results if r["success"]]
    return {
        "total": len(ips),
        "successful": len(successful),
        "original_address": original_address,
        "test_url": test_url,
        "results": results,
        "working_ips": successful,
    }