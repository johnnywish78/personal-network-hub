"""Latency measurements: ICMP-like ping via sockets and HTTP timing."""

from __future__ import annotations

import socket
import struct
import time
from typing import Optional


def ping(address: str, count: int = 4, timeout: float = 2.0, port: Optional[int] = None) -> dict:
    """Best-effort latency measurement.

    Prefers a raw ICMP echo if permitted; falls back to a TCP connect on
    the given port (default 443) when ICMP requires privileges.
    """
    if port:
        return tcp_ping(address, port, count, timeout)
    # Try ICMP first; catch permission errors and fall back to TCP 443.
    result = icmp_ping(address, count, timeout)
    if result.get("status") == "ok":
        return result
    return tcp_ping(address, 443, count, timeout)


def icmp_ping(address: str, count: int, timeout: float) -> dict:
    latencies: list[float] = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except PermissionError:
        return {"status": "no_permission", "latencies": [], "average_ms": None, "error": "ICMP requires privileges"}
    except OSError as exc:
        return {"status": "error", "latencies": [], "average_ms": None, "error": str(exc)}
    try:
        ip = socket.gethostbyname(address)
        sock.settimeout(timeout)
        for seq in range(count):
            ident = int(time.monotonic() * 1000) & 0xFFFF
            payload = struct.pack(">d", time.time()) + b"JPNH" * 12
            header = struct.pack(">BBHHH", 8, 0, 0, ident, seq)
            checksum = _icmp_checksum(header + payload)
            header = struct.pack(">BBHHH", 8, 0, checksum, ident, seq)
            start = time.monotonic()
            try:
                sock.sendto(header + payload, (ip, 0))
                sock.recvfrom(2048)
                latencies.append(round((time.monotonic() - start) * 1000, 1))
            except socket.timeout:
                continue
            time.sleep(0.2)
        sock.close()
        if latencies:
            return {"status": "ok", "latencies": latencies, "average_ms": round(sum(latencies) / len(latencies), 1),
                    "loss_pct": round((count - len(latencies)) / count * 100)}
        return {"status": "timeout", "latencies": [], "average_ms": None, "loss_pct": 100}
    except OSError as exc:
        return {"status": "error", "latencies": [], "average_ms": None, "error": str(exc)}
    finally:
        try:
            sock.close()
        except Exception:
            pass


def tcp_ping(address: str, port: int, count: int, timeout: float) -> dict:
    latencies: list[float] = []
    errors: list[str] = []
    for _ in range(count):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        start = time.monotonic()
        try:
            sock.connect((address, port))
            latencies.append(round((time.monotonic() - start) * 1000, 1))
        except socket.timeout:
            errors.append("timeout")
        except OSError as exc:
            errors.append(str(exc))
        finally:
            sock.close()
        time.sleep(0.2)
    if latencies:
        return {"status": "ok", "latencies": latencies, "average_ms": round(sum(latencies) / len(latencies), 1),
                "port": port, "loss_pct": round((count - len(latencies)) / count * 100)}
    return {"status": "error", "latencies": [], "average_ms": None, "port": port, "error": errors[0] if errors else "unknown"}


def _icmp_checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        total += (data[i] << 8) + data[i + 1]
    total = (total >> 16) + (total & 0xFFFF)
    total += total >> 16
    return (~total) & 0xFFFF
