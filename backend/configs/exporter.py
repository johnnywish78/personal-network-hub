"""Config exporter.

Produces share links (single / multiple), JSON dumps, and TXT bundles.
Transformations are explicit and reported to the caller; the original
configuration is never silently modified.
"""

from __future__ import annotations

import json
from typing import Optional

from .model import NormalizedConfig
from .normalizer import to_uri


def export_uris(configs: list[NormalizedConfig]) -> str:
    """One share link per line, preserving original raw config when available."""
    lines: list[str] = []
    for cfg in configs:
        uri = _preferred_uri(cfg)
        if uri:
            lines.append(uri)
    return "\n".join(lines)


def export_json(configs: list[NormalizedConfig], include_private: bool = False) -> str:
    payload = []
    for cfg in configs:
        data = cfg.model_dump(mode="json")
        if not include_private:
            data.pop("private_key", None)
        payload.append(data)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def export_xray_config(cfg: NormalizedConfig) -> str:
    """Convert a normalized config to an Xray client outbound JSON if possible."""
    outbound = _to_xray_outbound(cfg)
    if outbound is None:
        raise ValueError(f"cannot export {cfg.protocol or 'unknown'} protocol to Xray JSON")
    xray = {
        "log": {"loglevel": "warning"},
        "inbounds": [],
        "outbounds": [outbound],
        "dns": {"servers": ["1.1.1.1", "8.8.8.8"]},
    }
    return json.dumps(xray, ensure_ascii=False, indent=2)


def export_txt(configs: list[NormalizedConfig]) -> str:
    """Human-readable export with metadata per config."""
    parts: list[str] = []
    for i, cfg in enumerate(configs, 1):
        parts.append(f"[{i}] {cfg.name}")
        parts.append(f"    protocol : {cfg.protocol or '-'}")
        parts.append(f"    address  : {cfg.address or '-'}:{cfg.port or '-'}")
        parts.append(f"    security : {cfg.security or '-'}")
        parts.append(f"    status   : {cfg.status.value}  ({cfg.latency_ms} ms)" if cfg.latency_ms else f"    status   : {cfg.status.value}")
        uri = _preferred_uri(cfg)
        if uri:
            parts.append(f"    uri      : {uri}")
        parts.append("")
    return "\n".join(parts).strip()


def _preferred_uri(cfg: NormalizedConfig) -> Optional[str]:
    if cfg.raw_config and any(cfg.raw_config.startswith(s) for s in
                              ("vless://", "trojan://", "vmess://", "ss://", "hysteria2://", "hy2://")):
        return cfg.raw_config
    return to_uri(cfg)


def _to_xray_outbound(cfg: NormalizedConfig) -> Optional[dict]:
    proto = cfg.protocol
    if proto == "vless":
        return {
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": cfg.address,
                    "port": cfg.port,
                    "users": [{"id": cfg.uuid, "flow": cfg.flow or ""}],
                }]
            },
            "streamSettings": _stream_settings(cfg),
        }
    if proto == "trojan":
        return {
            "protocol": "trojan",
            "settings": {
                "servers": [{"address": cfg.address, "port": cfg.port, "password": cfg.password}]
            },
            "streamSettings": _stream_settings(cfg),
        }
    if proto == "vmess":
        return {
            "protocol": "vmess",
            "settings": {
                "vnext": [{
                    "address": cfg.address,
                    "port": cfg.port,
                    "users": [{"id": cfg.uuid, "security": "auto"}],
                }]
            },
            "streamSettings": _stream_settings(cfg),
        }
    return None


def _stream_settings(cfg: NormalizedConfig) -> dict:
    network = cfg.network or "tcp"
    security = cfg.security or "none"
    stream: dict = {"network": network, "security": security}
    if security == "tls":
        tls_settings: dict = {}
        if cfg.sni:
            tls_settings["serverName"] = cfg.sni
        if cfg.fingerprint:
            tls_settings["fingerprint"] = cfg.fingerprint
        if cfg.alpn:
            tls_settings["alpn"] = cfg.alpn
        stream["tlsSettings"] = tls_settings
    if security == "reality":
        reality: dict = {"show": False}
        if cfg.sni:
            reality["serverName"] = cfg.sni
        if cfg.fingerprint:
            reality["fingerprint"] = cfg.fingerprint
        if cfg.public_key:
            reality["publicKey"] = cfg.public_key
        if cfg.short_id:
            reality["shortId"] = cfg.short_id
        stream["realitySettings"] = reality
    if network == "ws":
        ws: dict = {}
        if cfg.path:
            ws["path"] = cfg.path
        if cfg.host:
            ws["headers"] = {"Host": cfg.host}
        stream["wsSettings"] = ws
    if network in ("xhttp", "httpupgrade"):
        stream["network"] = network
        if cfg.path:
            stream["xhttpSettings"] = {"path": cfg.path, "host": cfg.host or ""}
    if network == "grpc":
        stream["grpcSettings"] = {"serviceName": cfg.service_name or ""}
    return stream
