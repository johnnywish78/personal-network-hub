"""Shared helpers for the Network Checker port.

Algorithms ported from the GPL-3.0 mirarr-app/network-checker Flutter app
(vendored under third_party/network-checker). Behavior mirrors the upstream
Dart implementations (timeouts, CIDR expansion rules, DNS packet parsing).
"""

from __future__ import annotations

import socket
import ssl
import struct
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

_TIMEOUT_DEFAULT = 3.0


def ip_to_int(ip: str) -> Optional[int]:
    try:
        parts = [int(p) for p in ip.split(".")]
    except (ValueError, AttributeError):
        return None
    if len(parts) != 4 or any(p < 0 or p > 255 for p in parts):
        return None
    return (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]


def int_to_ip(value: int) -> str:
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def is_valid_ipv4(ip: str) -> bool:
    return ip_to_int(ip) is not None


def is_private_or_reserved_ipv4(ip: str) -> bool:
    """Mirrors the upstream private/reserved IPv4 checks."""
    parts = ip.split(".")
    if len(parts) != 4:
        return True
    try:
        a, b, c, d = (int(p) for p in parts)
    except ValueError:
        return True
    if a == 10:
        return True
    if a == 192 and b == 168:
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 127:
        return True
    if a == 0:
        return True
    if a >= 224:
        return True
    if a == 169 and b == 254:
        return True
    return False


def is_known_hijack_ip(ip: str) -> bool:
    return ip in {"127.0.0.1", "0.0.0.0", "10.10.34.34"}


def generate_ips_from_subnet(subnet: str, max_hosts: int = 1 << 16) -> list[str]:
    """Expand a CIDR into a list of usable host IPs.

    Mirrors the upstream edge/akamai scanners: excludes network and broadcast
    addresses for prefixes smaller than /31.
    """
    parts = subnet.split("/")
    if len(parts) != 2:
        return []
    prefix = _safe_int(parts[1])
    if prefix is None or prefix < 0 or prefix > 32:
        return []
    base = ip_to_int(parts[0])
    if base is None:
        return []

    host_bits = 32 - prefix
    num_hosts = 1 << host_bits
    if num_hosts > max_hosts:
        num_hosts = max_hosts

    netmask = ~((1 << host_bits) - 1) & 0xFFFFFFFF
    network_addr = base & netmask

    start = 0 if prefix >= 31 else 1
    end = num_hosts if prefix >= 31 else num_hosts - 1
    if end - start <= 0:
        return []

    ips: list[str] = []
    for i in range(start, end):
        addr = network_addr + i
        ips.append(int_to_ip(addr & 0xFFFFFFFF))
    return ips


def expand_cidr_limits(cidr: str, max_ips: int = 100000) -> list[str]:
    """VLESS-style CIDR expansion (from vless_config_modifier_controller)."""
    parts = cidr.split("/")
    if len(parts) != 2:
        return [cidr]
    prefix = _safe_int(parts[1])
    base = ip_to_int(parts[0])
    if prefix is None or base is None or prefix < 0 or prefix > 32:
        return [cidr]

    host_bits = 32 - prefix
    host_count = 1 << host_bits
    network_addr = base & (0xFFFFFFFF << host_bits)

    start_offset = 1 if host_bits >= 8 else 0
    end_offset = (host_count - 1) if host_bits >= 8 else host_count
    actual_end = start_offset + max_ips if (end_offset - start_offset) > max_ips else end_offset

    ips: list[str] = []
    for i in range(start_offset, actual_end):
        addr = (network_addr + i) & 0xFFFFFFFF
        ips.append(int_to_ip(addr))
    return ips


def expand_ip_range(start_ip: str, end_ip: str, max_ips: int = 100000) -> list[str]:
    start = ip_to_int(start_ip)
    end = ip_to_int(end_ip)
    if start is None or end is None or end < start:
        return [start_ip]
    actual_end = start + max_ips if (end - start) > max_ips else end
    return [int_to_ip(i & 0xFFFFFFFF) for i in range(start, actual_end + 1)]


def parse_ip_input(text: str) -> list[str]:
    """Parse IP/CIDR/port lines. Mirrors EdgeIpScanner.parseIpInput."""
    ips: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "/" in line:
            try:
                ips.extend(generate_ips_from_subnet(line))
            except Exception:
                continue
        else:
            if ":" in line:
                ip_part, _, port_part = line.partition(":")
                port = _safe_int(port_part)
                if port is not None and 0 < port <= 65535 and is_valid_ipv4(ip_part):
                    ips.append(line)
            elif is_valid_ipv4(line):
                ips.append(line)
    return ips


def _safe_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def batched_executor(items: list, worker: Callable, concurrency: int) -> list:
    """Run `worker(item)` in concurrency-sized batches (upstream batching)."""
    results: list = []
    for i in range(0, len(items), concurrency):
        batch = items[i:i + concurrency]
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results.extend(pool.map(worker, batch))
    return results


# --- DNS over UDP ----------------------------------------------------------

def build_dns_query(domain: str, txn: int = 0xABCD) -> bytes:
    """Minimal DNS A query packet (upstream dns_hunter_service format)."""
    header = struct.pack(">HHHHHH", txn, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(label)]) + label.encode("ascii") for label in domain.split("."))
    return header + qname + b"\x00" + struct.pack(">HH", 1, 1)


def parse_dns_response(data: bytes) -> dict:
    """Parse A-record answers. Returns {rcode, is_nxdomain, ips}."""
    if len(data) < 12:
        return {"rcode": None, "is_nxdomain": False, "ips": []}
    if (data[2] & 0x80) == 0:
        return {"rcode": None, "is_nxdomain": False, "ips": []}
    rcode = data[3] & 0x0F
    answer_count = (data[6] << 8) | data[7]
    offset = 12

    while offset < len(data) and data[offset] != 0:
        if (data[offset] & 0xC0) == 0xC0:
            offset += 2
            break
        offset += data[offset] + 1
    offset += 1 + 4  # null terminator + qtype/qclass

    ips: list[str] = []
    for _ in range(answer_count):
        if offset + 12 > len(data):
            break
        if (data[offset] & 0xC0) == 0xC0:
            offset += 2
        else:
            while offset < len(data) and data[offset] != 0:
                offset += data[offset] + 1
            offset += 1
        rtype, _rclass, _ttl, rdlength = struct.unpack(">HHIH", data[offset:offset + 10])
        offset += 10
        if rtype == 1 and rdlength == 4 and offset + 4 <= len(data):
            ips.append(".".join(str(b) for b in data[offset:offset + 4]))
        offset += rdlength
    return {"rcode": rcode, "is_nxdomain": rcode == 3, "ips": ips}


def udp_dns_query(ip: str, domain: str, timeout: float = 2.0, txn: Optional[int] = None) -> dict:
    """Query a DNS server over UDP for an A record. Returns a result dict."""
    txn_id = txn if txn is not None else 0xABCD
    start = time.monotonic()
    if not is_valid_ipv4(ip):
        return {"success": False, "latency_ms": None, "ips": [], "error": "Invalid IP address"}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(build_dns_query(domain, txn_id), (ip, 53))
        data, _addr = sock.recvfrom(4096)
        elapsed_ms = (time.monotonic() - start) * 1000
        if len(data) < 2 or data[0] != (txn_id >> 8) or data[1] != (txn_id & 0xFF):
            return {"success": False, "latency_ms": None, "ips": [], "error": "Mismatched transaction ID"}
        parsed = parse_dns_response(data)
        return {
            "success": parsed["rcode"] == 0,
            "latency_ms": round(elapsed_ms, 1),
            "ips": parsed["ips"],
            "is_nxdomain": parsed["is_nxdomain"],
            "rcode": parsed["rcode"],
            "error": None if parsed["rcode"] in (0, 3) else f"DNS RCODE {parsed['rcode']}",
        }
    except socket.timeout:
        return {"success": False, "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "ips": [], "error": "Timeout"}
    except OSError as exc:
        return {"success": False, "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "ips": [], "error": _friendly_os_error(exc)}
    finally:
        sock.close()


def tcp_connect(address: str, port: int, timeout: float = _TIMEOUT_DEFAULT) -> dict:
    """TCP connect test. Returns {reachable, latency_ms, error}."""
    start = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((address, port))
        latency = round((time.monotonic() - start) * 1000, 1)
        return {"reachable": True, "latency_ms": latency, "error": None}
    except socket.timeout:
        return {"reachable": False, "latency_ms": None, "error": "Connection timed out"}
    except OSError as exc:
        return {"reachable": False, "latency_ms": None, "error": _friendly_os_error(exc)}
    finally:
        sock.close()


def tls_handshake(address: str, port: int, sni: str, timeout: float = _TIMEOUT_DEFAULT) -> dict:
    """TLS handshake (accepts any cert). Returns handshake + cert metadata."""
    start = time.monotonic()
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((address, port))
        tls = context.wrap_socket(sock, server_hostname=sni)
        latency = round((time.monotonic() - start) * 1000, 1)
        cert = tls.getpeercert()
        return {
            "reachable": True,
            "latency_ms": latency,
            "protocol": tls.version(),
            "cert": cert,
            "error": None,
        }
    except ssl.SSLError as exc:
        return {"reachable": False, "latency_ms": None, "cert": None,
                "error": f"SSL/TLS handshake failed: {exc}"}
    except socket.timeout:
        return {"reachable": False, "latency_ms": None, "cert": None, "error": "Connection timed out"}
    except OSError as exc:
        return {"reachable": False, "latency_ms": None, "cert": None, "error": _friendly_os_error(exc)}
    finally:
        sock.close()


def _friendly_os_error(exc: OSError) -> str:
    message = str(exc).lower()
    if "network is unreachable" in message:
        return "Network unreachable"
    if "no route to host" in message:
        return "No route to host"
    if "connection refused" in message:
        return "Connection refused"
    if "connection reset" in message:
        return "Connection reset by peer"
    if "permission denied" in message:
        return "Permission denied"
    if len(str(exc)) > 100:
        return str(exc)[:97] + "..."
    return str(exc)