"""TCP and TLS reachability checks with timing.

These tests verify REACHABILITY only. They do not prove a proxy config
works end-to-end (see config_test.py for the full pipeline).
"""

from __future__ import annotations

import socket
import ssl
import time
from typing import Optional

from .errors import friendly_with_detail


def tcp_check(address: str, port: int, timeout: float = 5.0) -> dict:
    """Test whether a TCP connection can be established to address:port."""
    start = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((address, port))
        elapsed = (time.monotonic() - start) * 1000
        return {"address": address, "port": port, "reachable": True,
                "latency_ms": round(elapsed, 1), "error": None}
    except socket.timeout:
        return {"address": address, "port": port, "reachable": False,
                "latency_ms": None, "error": "Connection timed out — host is unreachable or filtered."}
    except OSError as exc:
        return {"address": address, "port": port, "reachable": False,
                "latency_ms": None, "error": friendly_with_detail(str(exc))}
    finally:
        sock.close()


def tls_check(address: str, port: int, sni: Optional[str] = None, timeout: float = 5.0) -> dict:
    """Test whether a TLS handshake completes. Returns negotiated protocol."""
    start = time.monotonic()
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((address, port))
        tls_sock = context.wrap_socket(sock, server_hostname=sni or address)
        elapsed = (time.monotonic() - start) * 1000
        version = tls_sock.version()
        cipher = tls_sock.cipher()
        tls_sock.close()
        return {"address": address, "port": port, "tls_ok": True,
                "latency_ms": round(elapsed, 1), "version": version,
                "cipher": cipher[0] if cipher else None, "error": None}
    except socket.timeout:
        return {"address": address, "port": port, "tls_ok": False,
                "latency_ms": None, "error": "TLS handshake timed out — host is unreachable or filtered."}
    except ssl.SSLError as exc:
        return {"address": address, "port": port, "tls_ok": False,
                "latency_ms": None, "error": friendly_with_detail(f"TLS handshake failed: {exc}")}
    except OSError as exc:
        return {"address": address, "port": port, "tls_ok": False,
                "latency_ms": None, "error": friendly_with_detail(str(exc))}
    finally:
        sock.close()
