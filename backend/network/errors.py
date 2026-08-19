"""Human-readable error mapping for common network failures.

Raw exceptions like `[Errno 104] Connection reset by peer` are mapped to
clear messages while the diagnostic detail stays visible.
"""

from __future__ import annotations

import errno
from typing import Optional

_ERRNO_MAP = {
    errno.ECONNRESET: "Connection reset by remote — the endpoint rejected the handshake or the path is blocked.",
    errno.ETIMEDOUT: "Connection timed out — host is unreachable or filtered.",
    errno.ECONNREFUSED: "Connection refused — nothing is listening on that port.",
    errno.EHOSTUNREACH: "Host unreachable — no route to the target.",
    errno.ENETUNREACH: "Network unreachable — no route to the network.",
    errno.EPERM: "Operation not permitted — the local network stack blocked the request.",
    errno.EACCES: "Permission denied — the local network stack blocked the request.",
    errno.EADDRNOTAVAIL: "Address not available — the target address cannot be used.",
}


def friendly_error(message: Optional[str]) -> str:
    """Convert an OS-level error string into a clear message."""
    if not message:
        return "unknown error"
    lowered = message.lower()
    for code, friendly in _ERRNO_MAP.items():
        if f"[errno {code}]" in lowered:
            return friendly
    if "timeout" in lowered:
        return "Operation timed out — the target did not respond in time."
    if "reset" in lowered:
        return "Connection reset by remote — the endpoint rejected the handshake or the path is blocked."
    if "refused" in lowered:
        return "Connection refused — nothing is listening on that port."
    if "unreachable" in lowered:
        return "Host unreachable — no route to the target."
    return message


def friendly_with_detail(message: Optional[str]) -> str:
    """Friendly message with the raw detail appended in parentheses."""
    if not message:
        return "unknown error"
    friendly = friendly_error(message)
    if friendly == message:
        return message
    return f"{friendly} (detail: {message})"