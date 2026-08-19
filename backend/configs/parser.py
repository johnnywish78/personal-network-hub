"""Configuration parsers.

Supports:
  * VLESS URIs (vless://...)
  * Trojan URIs (trojan://...)
  * VMess URIs (vmess://<base64 JSON>)
  * Shadowsocks URIs (ss://...)
  * WireGuard-ish URI fragments (wg://) where present
  * Subscription URLs (http(s):// ... containing share links)
  * Xray / sing-box JSON configs (extracts first usable outbound)
  * Multiple share-links separated by newlines

Parsers never throw on malformed input; they return None or a dict with
`error` so callers can surface a clean message.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from typing import Any, Optional

SUPPORTED_SCHEMES = {"vless", "vmess", "trojan", "ss", "ssr", "wireguard", "wg", "hysteria2", "hy2", "tuic"}


def parse_many(payload: str) -> list[dict[str, Any]]:
    """Parse a payload that may contain multiple share links.

    Returns a list of parsed dicts. Entries with a non-null `error` failed.
    """
    payload = payload.strip()
    if not payload:
        return []
    if looks_like_json(payload):
        return [_parse_json(payload)]
    # Split on whitespace/newlines, also tolerate comma separators.
    lines = re.split(r"[\r\n]+", payload)
    results: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parsed = parse_single(line)
        if parsed is not None:
            results.append(parsed)
    return results


def parse_single(uri: str) -> Optional[dict[str, Any]]:
    """Parse one share link or JSON config."""
    if looks_like_json(uri):
        return _parse_json(uri)
    try:
        parsed = urllib.parse.urlparse(uri)
    except ValueError:
        return {"error": "malformed URI"}
    scheme = parsed.scheme.lower()
    if scheme == "vless":
        return _parse_vless(uri)
    if scheme == "trojan":
        return _parse_trojan(uri)
    if scheme == "vmess":
        return _parse_vmess(uri)
    if scheme == "ss":
        return _parse_shadowsocks(uri)
    if scheme in ("hysteria2", "hy2"):
        return _parse_hysteria2(uri)
    if scheme == "tuic":
        return {"error": "tuic parsing not implemented", "raw_config": uri}
    if scheme in ("wireguard", "wg"):
        return _parse_wireguard(uri)
    if scheme in ("http", "https"):
        return {"source": "subscription", "subscription_url": uri, "raw_config": uri}
    return {"error": f"unsupported scheme: {scheme or '(none)'}", "raw_config": uri}


def looks_like_json(payload: str) -> bool:
    payload = payload.strip()
    return payload.startswith("{") or payload.startswith("[")


# --- JSON (Xray / sing-box) -------------------------------------------

def _parse_json(payload: str) -> dict[str, Any]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        return {"error": f"invalid JSON: {exc}"}
    outbound = _find_outbound(data)
    if outbound is None:
        return {"error": "no usable outbound found in JSON"}
    return _normalize_outbound(outbound, payload)


def _find_outbound(data: Any) -> Optional[dict[str, Any]]:
    if isinstance(data, list):
        for item in data:
            found = _find_outbound(item)
            if found:
                return found
        return None
    if not isinstance(data, dict):
        return None
    for key in ("outbound", "outbounds"):
        value = data.get(key)
        if isinstance(value, list) and value:
            for ob in value:
                if isinstance(ob, dict) and ob.get("protocol") not in (None, "blackhole", "freedom", "dns"):
                    return ob
            continue
        if isinstance(value, dict) and value.get("protocol") not in (None, "blackhole", "freedom", "dns"):
            return value
    return None


def _normalize_outbound(ob: dict[str, Any], raw: str) -> dict[str, Any]:
    protocol = ob.get("protocol", "").lower()
    settings = ob.get("settings") or {}
    stream = ob.get("streamSettings") or {}
    network = stream.get("network", "tcp")
    security = stream.get("security", "none")
    tls = stream.get("tlsSettings") or stream.get("realitySettings") or {}
    ws = stream.get("wsSettings") or {}
    xhttp = stream.get("xhttpSettings") or stream.get("xhttpServerSettings") or {}
    grpc = stream.get("grpcSettings") or {}

    result: dict[str, Any] = {"protocol": protocol, "raw_config": raw}
    vnext = (settings.get("vnext") or [{}])[0]
    servers = settings.get("servers") or [{}]
    result["address"] = vnext.get("address") or servers[0].get("address")
    result["port"] = vnext.get("port") or servers[0].get("port")
    user0 = (vnext.get("users") or [{}])[0]
    result["uuid"] = user0.get("id")
    result["security"] = security or None
    result["sni"] = tls.get("serverName")
    result["fingerprint"] = tls.get("fingerprint")
    result["alpn"] = tls.get("alpn") or []
    result["network"] = network
    result["host"] = ws.get("host") or xhttp.get("host")
    result["path"] = ws.get("path") or xhttp.get("path") or grpc.get("serviceName")
    result["service_name"] = grpc.get("serviceName")
    result["mode"] = xhttp.get("mode")
    result["flow"] = user0.get("flow")
    result["public_key"] = tls.get("publicKey") or (tls.get("settings") or {}).get("publicKey")
    result["short_id"] = tls.get("shortId")
    return result


# --- VLESS -------------------------------------------------------------

def _parse_vless(uri: str) -> dict[str, Any]:
    try:
        parsed = urllib.parse.urlparse(uri)
    except ValueError:
        return {"error": "malformed vless URI"}
    result: dict[str, Any] = {
        "protocol": "vless",
        "raw_config": uri,
    }
    if parsed.username:
        result["uuid"] = parsed.username
    if parsed.hostname:
        result["address"] = parsed.hostname
    if parsed.port:
        result["port"] = parsed.port

    params = _params(parsed)
    result["security"] = params.get("security")
    result["sni"] = params.get("sni")
    result["fingerprint"] = params.get("fp")
    result["flow"] = params.get("flow")
    result["type"] = params.get("type")
    result["network"] = params.get("type")
    result["host"] = params.get("host")
    result["path"] = params.get("path")
    result["mode"] = params.get("mode")
    result["service_name"] = params.get("serviceName")
    result["alpn"] = _split_csv(params.get("alpn"))
    result["public_key"] = params.get("pbk")
    result["short_id"] = params.get("sid")
    # name comes from the fragment
    fragment = urllib.parse.unquote(parsed.fragment or "").strip()
    if fragment:
        result["name"] = fragment
    if not result.get("uuid"):
        return {"error": "vless URI missing UUID", "raw_config": uri}
    return result


# --- Trojan ------------------------------------------------------------

def _parse_trojan(uri: str) -> dict[str, Any]:
    try:
        parsed = urllib.parse.urlparse(uri)
    except ValueError:
        return {"error": "malformed trojan URI"}
    result: dict[str, Any] = {
        "protocol": "trojan",
        "raw_config": uri,
    }
    if parsed.password or parsed.username:
        result["password"] = parsed.password or parsed.username
    if parsed.hostname:
        result["address"] = parsed.hostname
    if parsed.port:
        result["port"] = parsed.port
    params = _params(parsed)
    result["security"] = params.get("security", "tls")
    result["sni"] = params.get("sni")
    result["fingerprint"] = params.get("fp")
    result["alpn"] = _split_csv(params.get("alpn"))
    result["network"] = params.get("type", "tcp")
    result["host"] = params.get("host")
    result["path"] = params.get("path")
    result["service_name"] = params.get("serviceName")
    fragment = urllib.parse.unquote(parsed.fragment or "").strip()
    if fragment:
        result["name"] = fragment
    if not result.get("password"):
        return {"error": "trojan URI missing password", "raw_config": uri}
    return result


# --- VMess -------------------------------------------------------------

def _parse_vmess(uri: str) -> dict[str, Any]:
    result: dict[str, Any] = {"protocol": "vmess", "raw_config": uri}
    payload = uri[len("vmess://"):]
    payload = payload.split("#")[0].strip()
    try:
        decoded = _b64decode(payload)
        data = json.loads(decoded)
    except Exception:
        return {"error": "invalid vmess payload (expected base64 JSON)", "raw_config": uri}
    result["name"] = data.get("ps")
    result["address"] = data.get("add")
    result["port"] = data.get("port")
    result["uuid"] = data.get("id")
    result["security"] = data.get("scy") or data.get("security")
    result["network"] = data.get("net", "tcp")
    result["host"] = data.get("host")
    result["path"] = data.get("path")
    result["tls"] = data.get("tls")
    result["sni"] = data.get("sni")
    result["alpn"] = _split_csv(data.get("alpn"))
    result["flow"] = data.get("flow")
    result["service_name"] = data.get("serviceName")
    fragment = urllib.parse.unquote(uri.split("#")[-1] if "#" in uri else "")
    if fragment and not result.get("name"):
        result["name"] = fragment
    if not result.get("uuid") or not result.get("address"):
        return {"error": "vmess JSON missing id or address", "raw_config": uri}
    return result


# --- Shadowsocks --------------------------------------------------------

def _parse_shadowsocks(uri: str) -> dict[str, Any]:
    result: dict[str, Any] = {"protocol": "ss", "raw_config": uri}
    rest = uri[len("ss://"):]
    # sip002 style: ss://base64(method:password)@host:port?plugin=...#name
    try:
        parsed = urllib.parse.urlparse(uri)
    except ValueError:
        return {"error": "malformed ss URI"}
    try:
        userinfo = parsed.username or ""
        decoded_userinfo = _b64decode(userinfo) if not parsed.password else userinfo
    except Exception:
        decoded_userinfo = userinfo
    if parsed.password:
        method_pass = f"{parsed.username}:{parsed.password}" if ":" not in (parsed.username or "") else decoded_userinfo
        if ":" in decoded_userinfo:
            method, password = decoded_userinfo.split(":", 1)
        else:
            method, password = (parsed.username or ""), (parsed.password or "")
    else:
        if ":" not in decoded_userinfo:
            return {"error": "malformed ss userinfo", "raw_config": uri}
        method, password = decoded_userinfo.split(":", 1)
    result["method"] = method
    result["password"] = password
    result["address"] = parsed.hostname
    result["port"] = parsed.port
    params = _params(parsed)
    result["plugin"] = params.get("plugin")
    fragment = urllib.parse.unquote(parsed.fragment or "").strip()
    if fragment:
        result["name"] = fragment
    if not result.get("address") or not result.get("password"):
        return {"error": "incomplete ss config", "raw_config": uri}
    return result


# --- Hysteria2 ----------------------------------------------------------

def _parse_hysteria2(uri: str) -> dict[str, Any]:
    try:
        parsed = urllib.parse.urlparse(uri)
    except ValueError:
        return {"error": "malformed hysteria2 URI"}
    result: dict[str, Any] = {
        "protocol": "hysteria2",
        "raw_config": uri,
    }
    result["password"] = parsed.password or parsed.username
    result["address"] = parsed.hostname
    result["port"] = parsed.port
    params = _params(parsed)
    result["sni"] = params.get("sni")
    result["insecure"] = params.get("insecure")
    result["alpn"] = _split_csv(params.get("alpn"))
    result["obfs"] = params.get("obfs")
    result["obfs_password"] = params.get("obfs-password")
    fragment = urllib.parse.unquote(parsed.fragment or "").strip()
    if fragment:
        result["name"] = fragment
    if not result.get("address"):
        return {"error": "missing address", "raw_config": uri}
    return result


# --- WireGuard ----------------------------------------------------------

def _parse_wireguard(uri: str) -> dict[str, Any]:
    try:
        parsed = urllib.parse.urlparse(uri)
    except ValueError:
        return {"error": "malformed wireguard URI"}
    result: dict[str, Any] = {
        "protocol": "wireguard",
        "raw_config": uri,
    }
    result["address"] = parsed.hostname
    result["port"] = parsed.port
    params = _params(parsed)
    result["public_key"] = params.get("publickey") or params.get("pubkey")
    result["private_key"] = params.get("privatekey")
    result["server_name"] = parsed.hostname
    result["mtu"] = _int_or_none(params.get("mtu"))
    result["allowed_ips"] = params.get("allowedips", "").split(",")
    fragment = urllib.parse.unquote(parsed.fragment or "").strip()
    if fragment:
        result["name"] = fragment
    if not result.get("address"):
        return {"error": "missing address", "raw_config": uri}
    return result


# --- helpers ------------------------------------------------------------

def _params(parsed: urllib.parse.ParseResult) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in urllib.parse.parse_qsl(parsed.query):
        if value and not out.get(key):
            out[key] = value
    return out


def _split_csv(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _b64decode(payload: str) -> str:
    padded = payload + "=" * ((4 - len(payload) % 4) % 4)
    raw = base64.b64decode(padded)
    return raw.decode("utf-8")


def _int_or_none(value: Optional[str]) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
