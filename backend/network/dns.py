"""DNS resolution and latency testing.

Includes a minimal, dependency-free DNS client that queries a specific
resolver over UDP (so we can test latency against 1.1.1.1, 8.8.8.8, etc.)
as well as a system-resolver fallback.
"""

from __future__ import annotations

import random
import socket
import struct
import time
from typing import Optional

SYSTEM = "system"
PUBLIC_RESOLVERS = ["1.1.1.1", "8.8.8.8", "9.9.9.9", "1.1.1.2", "8.8.4.4"]

_MAX_PACKET = 4096
_TIMEOUT = 3.0


def _build_query(name: str, qtype: int = 1, txn_id: Optional[int] = None) -> tuple[bytes, int]:
    """Build a DNS query. Returns (packet, transaction_id)."""
    txn = txn_id or random.randint(0, 0xFFFF)
    header = struct.pack(">HHHHHH", txn, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(part)]) + part.encode("ascii") for part in name.rstrip(".").split(".")) + b"\x00"
    question = qname + struct.pack(">HH", qtype, 1)
    return header + question, txn


def _parse_answer(packet: bytes, qtype: int = 1) -> list[str]:
    """Extract A (1) or AAAA (28) records from a response."""
    answers: list[str] = []
    try:
        # header: 2 flags + 4 counts
        qdcount, ancount = struct.unpack(">HH", packet[4:8])
    except struct.error:
        return []
    offset = 12
    for _ in range(qdcount):
        # skip qname
        while packet[offset] != 0:
            offset += packet[offset] + 1
        offset += 5  # null byte + qtype + qclass
    for _ in range(ancount):
        if offset + 10 > len(packet):
            break
        if (packet[offset] & 0xC0) == 0xC0:
            offset += 2  # compressed name pointer
        else:
            while packet[offset] != 0:
                offset += packet[offset] + 1
            offset += 1
        rtype, rclass, ttl, rdlength = struct.unpack(">HHIH", packet[offset:offset + 10])
        offset += 10
        if rtype == qtype and offset + rdlength <= len(packet):
            rdata = packet[offset:offset + rdlength]
            if qtype == 1 and rdlength == 4:
                answers.append(".".join(str(b) for b in rdata))
            elif qtype == 28 and rdlength == 16:
                answers.append(socket.inet_ntop(socket.AF_INET6, rdata))
        offset += rdlength
    return answers


def query_host(name: str, resolver: str = SYSTEM, timeout: float = _TIMEOUT) -> dict:
    """Resolve `name` and return timing info.

    resolver: SYSTEM uses the OS resolver; otherwise an IP of a DNS server.
    """
    start = time.monotonic()
    try:
        if resolver == SYSTEM:
            infos = socket.getaddrinfo(name, None, type=socket.SOCK_STREAM)
            ips = sorted({info[4][0] for info in infos})
            elapsed = (time.monotonic() - start) * 1000
            return {"host": name, "resolver": SYSTEM, "ips": ips, "latency_ms": round(elapsed, 1),
                    "status": "ok" if ips else "no records"}
        # custom resolver
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        packet, txn = _build_query(name)
        sock.sendto(packet, (resolver, 53))
        while True:
            data, _ = sock.recvfrom(_MAX_PACKET)
            response_id = struct.unpack(">H", data[0:2])[0]
            if response_id == txn:
                break
        elapsed = (time.monotonic() - start) * 1000
        ips = _parse_answer(data, 1)
        sock.close()
        return {"host": name, "resolver": resolver, "ips": ips, "latency_ms": round(elapsed, 1),
                "status": "ok" if ips else "no A records"}
    except socket.timeout:
        return {"host": name, "resolver": resolver, "ips": [], "latency_ms": None,
                "status": "timeout"}
    except socket.gaierror as exc:
        return {"host": name, "resolver": resolver, "ips": [], "latency_ms": None,
                "status": "error", "error": str(exc)}
    except OSError as exc:
        return {"host": name, "resolver": resolver, "ips": [], "latency_ms": None,
                "status": "error", "error": str(exc)}


def dns_latency_multi(hosts: Optional[list[str]] = None, resolvers: Optional[list[str]] = None) -> list[dict]:
    """Test DNS latency for several host/resolver pairs in sequence."""
    hosts = hosts or ["cloudflare.com", "google.com", "github.com"]
    resolvers = resolvers or PUBLIC_RESOLVERS
    results = []
    for host in hosts:
        for resolver in resolvers:
            results.append(query_host(host, resolver))
    return results
