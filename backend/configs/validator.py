"""Config validation.

Validates a normalized config's structure and basic sanity BEFORE any
network test. Distinguishes structural errors (missing fields) from
reachability issues (handled by the test engine).
"""

from __future__ import annotations

import ipaddress
import re
import uuid as uuidlib
from typing import Optional

from .model import NormalizedConfig


def is_ip(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def is_domain(value: Optional[str]) -> bool:
    if not value:
        return False
    pattern = r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
    return bool(re.match(pattern, value))


def is_valid_uuid(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        uuidlib.UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False


def validate(cfg: NormalizedConfig) -> dict:
    """Return {'valid': bool, 'errors': [...], 'warnings': [...]}."""
    errors: list[str] = []
    warnings: list[str] = []

    if not cfg.protocol:
        errors.append("missing protocol")
    else:
        supported = {"vless", "vmess", "trojan", "ss", "wireguard", "hysteria2"}
        if cfg.protocol not in supported:
            warnings.append(f"protocol '{cfg.protocol}' not in the primary supported set")

    if not cfg.address:
        errors.append("missing address")
    elif not is_ip(cfg.address) and not is_domain(cfg.address):
        warnings.append(f"address '{cfg.address}' does not look like an IP or domain")

    if not cfg.port:
        errors.append("missing port")
    elif not (0 < int(cfg.port) <= 65535):
        errors.append(f"port {cfg.port} out of range")

    if cfg.protocol == "vless":
        if not cfg.uuid:
            errors.append("VLESS requires a UUID")
        elif not is_valid_uuid(cfg.uuid):
            warnings.append("UUID format does not look standard")

    if cfg.protocol == "trojan" and not cfg.password:
        errors.append("Trojan requires a password")

    if cfg.protocol == "vmess" and not cfg.uuid:
        errors.append("VMess requires an id/UUID")

    if cfg.protocol == "wireguard" and not cfg.public_key:
        warnings.append("WireGuard missing public key")

    if cfg.security and str(cfg.security).lower() not in ("tls", "reality", "none"):
        warnings.append(f"unusual security value: {cfg.security}")

    return {"valid": not errors, "errors": errors, "warnings": warnings}
