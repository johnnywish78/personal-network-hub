"""Config normalizer: converts raw parsed dicts into NormalizedConfig.

The original payload is always preserved in `raw_config` and is never
modified. Field mapping keeps provider-specific naming intact where
possible.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Optional

from .model import NormalizedConfig
from . import parser


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def slugify(name: str) -> str:
    name = re.sub(r"[^\w\- ]", "", name).strip()
    return name or "Unnamed"


def normalize(parsed: dict[str, Any], provider: Optional[str] = None, source: Optional[str] = None) -> NormalizedConfig:
    """Build a NormalizedConfig from a parser output dict.

    Non-`id` fields in `parsed` are copied onto the model so nothing from
    the parsed output is lost. Explicit normalization is applied for known
    keys.
    """
    raw = parsed.get("raw_config") or ""
    name = parsed.get("name") or parsed.get("ps") or _derive_name(parsed)
    now = utc_now_iso()

    config = NormalizedConfig(
        name=name,
        provider=provider or parsed.get("provider") or parsed.get("source"),
        protocol=parsed.get("protocol"),
        address=parsed.get("address"),
        port=parsed.get("port"),
        uuid=parsed.get("uuid"),
        password=parsed.get("password"),
        security=_clean_security(parsed.get("security") or parsed.get("tls")),
        sni=parsed.get("sni") or parsed.get("serverName"),
        fingerprint=parsed.get("fingerprint") or parsed.get("fp"),
        alpn=_as_list(parsed.get("alpn")),
        network=parsed.get("network") or parsed.get("type"),
        transport=parsed.get("transport"),
        host=parsed.get("host"),
        path=parsed.get("path"),
        mode=parsed.get("mode"),
        service_name=parsed.get("service_name") or parsed.get("serviceName"),
        flow=parsed.get("flow"),
        public_key=parsed.get("public_key") or parsed.get("pbk") or parsed.get("publicKey"),
        short_id=parsed.get("short_id") or parsed.get("sid") or parsed.get("shortId"),
        server_name=parsed.get("server_name"),
        private_key=parsed.get("private_key"),
        mtu=parsed.get("mtu"),
        allowed_ips=_as_list(parsed.get("allowed_ips")),
        raw_config=raw,
        source=source or parsed.get("source"),
        created_at=now,
        updated_at=now,
    )
    # Preserve any remaining parsed keys the model does not have explicitly.
    known = set(config.model_dump().keys())
    extras: dict[str, Any] = {}
    for key, value in parsed.items():
        if key not in known and value is not None:
            extras[key] = value
    if extras:
        object.__setattr__(config, "_extras", extras)
    return config


def _derive_name(parsed: dict[str, Any]) -> str:
    address = parsed.get("address")
    port = parsed.get("port")
    proto = parsed.get("protocol") or "config"
    if address and port:
        return f"{proto}-{address}:{port}"
    if address:
        return f"{proto}-{address}"
    return "Unnamed"


def _clean_security(value: Any) -> Optional[str]:
    if not value or str(value).lower() in ("none", "false", "0", ""):
        return None
    return str(value)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]


def to_uri(config: NormalizedConfig) -> Optional[str]:
    """Reconstruct a share URI from normalized fields (VLESS/Trojan).

    Only used when the original raw_config is not available or the user
    explicitly wants a rebuilt URI. Never mutates the config.
    """
    if config.raw_config and config.raw_config.startswith("vless://"):
        return config.raw_config
    if config.protocol == "vless" and config.uuid:
        return _build_vless_uri(config)
    if config.protocol == "trojan" and config.password:
        return _build_trojan_uri(config)
    return config.raw_config or None


def _build_vless_uri(cfg: NormalizedConfig) -> str:
    query: list[str] = []
    if cfg.security:
        query.append(f"security={cfg.security}")
    if cfg.sni:
        query.append(f"sni={cfg.sni}")
    if cfg.fingerprint:
        query.append(f"fp={cfg.fingerprint}")
    if cfg.network:
        query.append(f"type={cfg.network}")
    if cfg.host:
        query.append(f"host={cfg.host}")
    if cfg.path:
        query.append(f"path={cfg.path}")
    if cfg.mode:
        query.append(f"mode={cfg.mode}")
    if cfg.service_name:
        query.append(f"serviceName={cfg.service_name}")
    if cfg.flow:
        query.append(f"flow={cfg.flow}")
    if cfg.public_key:
        query.append(f"pbk={cfg.public_key}")
    if cfg.short_id:
        query.append(f"sid={cfg.short_id}")
    if cfg.alpn:
        query.append(f"alpn={','.join(cfg.alpn)}")
    qs = ("?" + "&".join(query)) if query else ""
    name = f"#{cfg.name}" if cfg.name else ""
    return f"vless://{cfg.uuid}@{cfg.address}:{cfg.port}{qs}{name}"


def _build_trojan_uri(cfg: NormalizedConfig) -> str:
    query: list[str] = []
    if cfg.sni:
        query.append(f"sni={cfg.sni}")
    if cfg.fingerprint:
        query.append(f"fp={cfg.fingerprint}")
    if cfg.network and cfg.network != "tcp":
        query.append(f"type={cfg.network}")
    if cfg.host:
        query.append(f"host={cfg.host}")
    if cfg.path:
        query.append(f"path={cfg.path}")
    if cfg.alpn:
        query.append(f"alpn={','.join(cfg.alpn)}")
    qs = ("?" + "&".join(query)) if query else ""
    name = f"#{cfg.name}" if cfg.name else ""
    return f"trojan://{cfg.password}@{cfg.address}:{cfg.port}{qs}{name}"
