"""Normalized configuration model shared across the whole application.

Every imported/generated configuration is converted into a
NormalizedConfig. The original payload is always preserved in `raw_config`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ConfigStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    TESTING = "TESTING"
    WORKING = "WORKING"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class TestResult(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    PARTIAL = "PARTIAL"


class NormalizedConfig(BaseModel):
    """Canonical internal representation of any supported configuration."""

    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex[:12])
    name: str = "Unnamed"
    provider: Optional[str] = None
    protocol: Optional[str] = None  # vless, vmess, trojan, wireguard, shadowtls, ...
    address: Optional[str] = None
    port: Optional[int] = None

    uuid: Optional[str] = None
    password: Optional[str] = None

    security: Optional[str] = None  # TLS / Reality / None
    sni: Optional[str] = None
    fingerprint: Optional[str] = None
    alpn: Optional[list[str]] = Field(default_factory=list)

    network: Optional[str] = None  # tcp, ws, grpc, httpupgrade, xhttp, quic...
    transport: Optional[str] = None
    host: Optional[str] = None
    path: Optional[str] = None
    mode: Optional[str] = None
    service_name: Optional[str] = None
    flow: Optional[str] = None

    public_key: Optional[str] = None
    short_id: Optional[str] = None
    server_name: Optional[str] = None

    # wireguard / general extras
    private_key: Optional[str] = None
    mtu: Optional[int] = None
    allowed_ips: Optional[list[str]] = Field(default_factory=list)

    raw_config: str = Field(default="", description="Original payload, never modified")
    source: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    group: Optional[str] = None

    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_tested_at: Optional[str] = None

    status: ConfigStatus = ConfigStatus.UNKNOWN
    latency_ms: Optional[float] = None
    error: Optional[str] = None

    def to_public_dict(self) -> dict[str, Any]:
        """Serializable form safe for the API/UI (no private keys unless asked)."""
        data = self.model_dump(exclude={"private_key"})
        if self.private_key:
            data["private_key_masked"] = self.private_key[:4] + "****"
        return data
