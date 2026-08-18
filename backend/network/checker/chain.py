"""Chain (Network Checker) — multi-hop Xray JSON generator.

Ported from the upstream proxy_parser_service.dart + chain_controller.dart
(GPL-3.0 mirarr-app/network-checker). Parses proxy share links
(vless/vmess/trojan/ss/socks/http) and assembles a chained multi-hop Xray
configuration with SOCKS/HTTP inbounds and dialerProxy routing. Pure
config generation - no network access.
"""

from __future__ import annotations

import base64
import json
import urllib.parse


class ProxyNode:
    def __init__(self, protocol: str, address: str, port: int,
                 id_or_password: str | None = None, alter_id: str | None = None,
                 cipher: str | None = None, network: str = "tcp",
                 security: str = "none", sni: str | None = None, path: str | None = None,
                 host: str | None = None, service_name: str | None = None,
                 mode: str | None = None, public_key: str | None = None,
                 short_id: str | None = None, spider_x: str | None = None,
                 fingerprint: str | None = None, flow: str | None = None,
                 encryption: str | None = None, alpn: list[str] | None = None,
                 header_type: str | None = None, remarks: str = ""):
        self.protocol = protocol
        self.address = address
        self.port = port
        self.id_or_password = id_or_password
        self.alter_id = alter_id
        self.cipher = cipher
        self.network = network
        self.security = security
        self.sni = sni
        self.path = path
        self.host = host
        self.service_name = service_name
        self.mode = mode
        self.public_key = public_key
        self.short_id = short_id
        self.spider_x = spider_x
        self.fingerprint = fingerprint
        self.flow = flow
        self.encryption = encryption
        self.alpn = alpn
        self.header_type = header_type
        self.remarks = remarks

    def to_xray_outbound(self, tag: str, dialer_proxy_tag: str | None = None) -> dict:
        outbound: dict = {"tag": tag, "protocol": self.protocol}

        if self.protocol == "vless":
            user: dict = {"id": self.id_or_password or "",
                          "encryption": (self.encryption or "none") or "none"}
            if self.flow:
                user["flow"] = self.flow
            outbound["settings"] = {"vnext": [{"address": self.address, "port": self.port,
                                               "users": [user]}]}
        elif self.protocol == "vmess":
            try:
                alter_id = int(self.alter_id) if self.alter_id else 0
            except (TypeError, ValueError):
                alter_id = 0
            outbound["settings"] = {"vnext": [{"address": self.address, "port": self.port,
                                               "users": [{"id": self.id_or_password or "",
                                                          "alterId": alter_id,
                                                          "security": self.cipher or "auto"}]}]}
        elif self.protocol == "trojan":
            outbound["settings"] = {"servers": [{"address": self.address, "port": self.port,
                                                 "password": self.id_or_password or ""}]}
        elif self.protocol == "shadowsocks":
            outbound["settings"] = {"servers": [{"address": self.address, "port": self.port,
                                                 "method": self.cipher or "aes-256-gcm",
                                                 "password": self.id_or_password or ""}]}
        elif self.protocol in ("socks", "http"):
            users = []
            if self.id_or_password:
                users.append({"user": self.id_or_password, "pass": self.encryption or ""})
            outbound["settings"] = {"servers": [{"address": self.address, "port": self.port,
                                                 "users": users}]}
        else:
            raise ValueError(f"Unsupported protocol: {self.protocol}")

        stream: dict = {"network": self.network, "security": self.security}
        if self.security == "tls":
            tls: dict = {}
            if self.sni:
                tls["serverName"] = self.sni
            if self.alpn:
                tls["alpn"] = self.alpn
            if self.fingerprint:
                tls["fingerprint"] = self.fingerprint
            stream["tlsSettings"] = tls
        elif self.security == "reality":
            reality: dict = {}
            if self.sni:
                reality["serverName"] = self.sni
            if self.public_key:
                reality["publicKey"] = self.public_key
            if self.short_id:
                reality["shortId"] = self.short_id
            if self.spider_x:
                reality["spiderX"] = self.spider_x
            if self.fingerprint:
                reality["fingerprint"] = self.fingerprint
            stream["realitySettings"] = reality

        if self.network == "ws":
            ws: dict = {}
            if self.path:
                ws["path"] = self.path
            if self.host:
                ws["headers"] = {"Host": self.host}
            stream["wsSettings"] = ws
        elif self.network == "grpc":
            grpc: dict = {}
            if self.service_name:
                grpc["serviceName"] = self.service_name
            if self.mode == "multi":
                grpc["multiMode"] = True
            stream["grpcSettings"] = grpc
        elif self.network in ("h2", "http"):
            http: dict = {}
            if self.path:
                http["path"] = self.path
            if self.host:
                http["host"] = [self.host]
            stream["httpSettings"] = http
        elif self.network == "kcp":
            kcp: dict = {}
            if self.header_type:
                kcp["header"] = {"type": self.header_type}
            stream["kcpSettings"] = kcp
        elif self.network == "quic":
            quic: dict = {}
            if self.header_type:
                quic["header"] = {"type": self.header_type}
            stream["quicSettings"] = quic

        if dialer_proxy_tag:
            stream["sockopt"] = {"dialerProxy": dialer_proxy_tag}

        outbound["streamSettings"] = stream
        return outbound


def _normalize_base64(value: str) -> str:
    normalized = value.replace("-", "+").replace("_", "/")
    while len(normalized) % 4 != 0:
        normalized += "="
    return normalized


def _decode_b64(value: str) -> str:
    try:
        return base64.b64decode(_normalize_base64(value)).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


def _parse_host_port(value: str) -> tuple[str, int]:
    last_colon = value.rfind(":")
    if last_colon == -1:
        raise ValueError(f"Invalid host:port string: {value}")
    host = value[:last_colon]
    try:
        port = int(value[last_colon + 1:])
    except ValueError as exc:
        raise ValueError(f"Invalid port in host:port string: {value[last_colon + 1:]}") from exc
    if port <= 0 or port > 65535:
        raise ValueError(f"Invalid port in host:port string: {value[last_colon + 1:]}")
    return host, port


def _parse_query_string(query: str) -> dict:
    params: dict[str, str] = {}
    if not query:
        return params
    for pair in query.split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        params[urllib.parse.unquote(key)] = urllib.parse.unquote(value)
    return params


def _parse_vless(link: str) -> ProxyNode:
    uri_part, _, fragment = link[8:].partition("#")
    remarks = urllib.parse.unquote(fragment) if fragment else "VLESS Node"
    main, _, query_string = uri_part.partition("?")
    uuid, _, host_port = main.partition("@")
    if not uuid or not host_port:
        raise ValueError('Invalid VLESS format: missing "@" separating UUID and host')
    host, port = _parse_host_port(host_port)
    q = _parse_query_string(query_string)
    alpn = q["alpn"].split(",") if q.get("alpn") else None
    return ProxyNode(
        protocol="vless", address=host, port=port, id_or_password=uuid,
        network=q.get("type") or q.get("network") or "tcp",
        security=q.get("security") or "none",
        sni=q.get("sni") or q.get("peer"),
        path=urllib.parse.unquote(q["path"]) if q.get("path") else None,
        host=q.get("host") or q.get("headerType"),
        service_name=q.get("serviceName"), mode=q.get("mode"),
        public_key=q.get("pbk") or q.get("publicKey"),
        short_id=q.get("sid") or q.get("shortId"),
        spider_x=q.get("spx") or q.get("spiderX"),
        fingerprint=q.get("fp") or q.get("fingerprint"),
        flow=q.get("flow"), encryption=q.get("encryption"),
        alpn=alpn, header_type=q.get("headerType"),
        remarks=remarks or "VLESS Node")


def _parse_trojan(link: str) -> ProxyNode:
    uri_part, _, fragment = link[9:].partition("#")
    remarks = urllib.parse.unquote(fragment) if fragment else "Trojan Node"
    main, _, query_string = uri_part.partition("?")
    password, _, host_port = main.partition("@")
    if not host_port:
        raise ValueError('Invalid Trojan format: missing "@" separating password and host')
    password = urllib.parse.unquote(password)
    host, port = _parse_host_port(host_port)
    q = _parse_query_string(query_string)
    alpn = q["alpn"].split(",") if q.get("alpn") else None
    return ProxyNode(
        protocol="trojan", address=host, port=port, id_or_password=password,
        network=q.get("type") or q.get("network") or "tcp",
        security=q.get("security") or "tls",
        sni=q.get("sni") or q.get("peer") or q.get("host"),
        path=urllib.parse.unquote(q["path"]) if q.get("path") else None,
        host=q.get("host"), service_name=q.get("serviceName"), mode=q.get("mode"),
        public_key=q.get("pbk") or q.get("publicKey"),
        short_id=q.get("sid") or q.get("shortId"),
        spider_x=q.get("spx") or q.get("spiderX"),
        fingerprint=q.get("fp") or q.get("fingerprint"),
        alpn=alpn, header_type=q.get("headerType"),
        remarks=remarks or "Trojan Node")


def _parse_vmess(link: str) -> ProxyNode:
    raw = link[8:].strip()

    if "@" not in raw:
        decoded = _decode_b64(raw)
        if decoded:
            try:
                data = json.loads(decoded)
                add = str(data.get("add") or "")
                port = int(data.get("port") or 443)
                vid = str(data.get("id") or "")
                if not add or not vid:
                    raise ValueError("VMess JSON missing address or id")
                tls = str(data.get("tls") or "none")
                sec = "tls" if tls in ("tls", "1") else ("reality" if tls == "reality" else "none")
                alpn_str = data.get("alpn")
                alpn = alpn_str.split(",") if alpn_str else None
                return ProxyNode(
                    protocol="vmess", address=add, port=port, id_or_password=vid,
                    alter_id=str(data.get("aid") or "0"),
                    cipher=str(data.get("scy") or data.get("cipher") or "auto"),
                    network=str(data.get("net") or "tcp"), security=sec,
                    sni=str(data.get("sni") or "") or str(data.get("host") or ""),
                    path=str(data.get("path") or "") or None,
                    host=str(data.get("host") or "") or None,
                    fingerprint=str(data.get("fp") or "") or None,
                    alpn=alpn, header_type=str(data.get("type") or "") or None,
                    remarks=str(data.get("ps") or "") or "VMess Node")
            except (ValueError, TypeError):
                pass

    uri_part, _, fragment = raw.partition("#")
    remarks = urllib.parse.unquote(fragment) if fragment else "VMess Node"
    main, _, query_string = uri_part.partition("?")
    uuid, _, host_port = main.partition("@")
    if not uuid or not host_port:
        raise ValueError('Invalid VMess URI format: missing "@" separating UUID and host')
    host, port = _parse_host_port(host_port)
    q = _parse_query_string(query_string)
    return ProxyNode(
        protocol="vmess", address=host, port=port, id_or_password=uuid,
        alter_id=q.get("aid") or q.get("alterId") or "0",
        cipher=q.get("scy") or q.get("cipher") or "auto",
        network=q.get("net") or q.get("type") or q.get("network") or "tcp",
        security=q.get("security") or q.get("tls") or "none",
        sni=q.get("sni") or q.get("peer") or q.get("host"),
        path=urllib.parse.unquote(q["path"]) if q.get("path") else None,
        host=q.get("host"), fingerprint=q.get("fp") or q.get("fingerprint"),
        remarks=remarks or "VMess Node")


def _parse_shadowsocks(link: str) -> ProxyNode:
    uri_part, _, fragment = link[5:].partition("#")
    remarks = urllib.parse.unquote(fragment) if fragment else "Shadowsocks Node"
    main, _, _ = uri_part.partition("?")
    q = _parse_query_string(uri_part.partition("?")[2])

    method = ""
    password = ""
    host = ""
    port = 8388

    if "@" in main:
        userinfo, _, host_port = main.partition("@")
        host, port = _parse_host_port(host_port)
        decoded = userinfo
        if ":" not in userinfo:
            decoded = _decode_b64(userinfo) or userinfo
        colon = decoded.find(":")
        if colon != -1:
            method = urllib.parse.unquote(decoded[:colon])
            password = urllib.parse.unquote(decoded[colon + 1:])
        else:
            password = urllib.parse.unquote(decoded)
    else:
        decoded = _decode_b64(main)
        if decoded and "@" in decoded:
            userinfo, _, host_port = decoded.partition("@")
            host, port = _parse_host_port(host_port)
            colon = userinfo.find(":")
            if colon != -1:
                method = urllib.parse.unquote(userinfo[:colon])
                password = urllib.parse.unquote(userinfo[colon + 1:])
            else:
                password = urllib.parse.unquote(userinfo)
        else:
            raise ValueError("Invalid Shadowsocks format")

    return ProxyNode(
        protocol="shadowsocks", address=host, port=port, id_or_password=password,
        cipher=method or "aes-256-gcm",
        remarks=remarks or "Shadowsocks Node")


def _parse_userinfo_link(link: str, default_port: int) -> tuple[str, str, str, int, str]:
    """Shared parse for socks/http links: returns remarks, username, host, port, password."""
    uri_part, _, fragment = link.partition("#")
    remarks = urllib.parse.unquote(fragment) if fragment else "SOCKS Node"
    main, _, _ = uri_part.partition("?")
    username = ""
    password = ""
    host = ""
    port = default_port
    if "@" in main:
        userinfo, _, host_port = main.partition("@")
        host, port = _parse_host_port(host_port)
        decoded = userinfo
        if ":" not in userinfo:
            decoded = _decode_b64(userinfo) or userinfo
        colon = decoded.find(":")
        if colon != -1:
            username = urllib.parse.unquote(decoded[:colon])
            password = urllib.parse.unquote(decoded[colon + 1:])
        else:
            username = urllib.parse.unquote(decoded)
    else:
        host, port = _parse_host_port(main)
    return remarks, username, host, port, password


def _parse_socks(link: str) -> ProxyNode:
    prefix = 9 if link.startswith("socks5://") else 8
    remarks, username, host, port, password = _parse_userinfo_link(link[prefix:], 1080)
    return ProxyNode(protocol="socks", address=host, port=port,
                     id_or_password=username, encryption=password,
                     remarks=remarks or "SOCKS Node")


def _parse_http(link: str) -> ProxyNode:
    is_https = link.startswith("https://")
    prefix = 8 if is_https else 7
    remarks, username, host, port, password = _parse_userinfo_link(
        link[prefix:], 443 if is_https else 80)
    main, _, query = link[prefix:].partition("?")
    q = _parse_query_string(query)
    sni = q.get("sni") or q.get("peer") or host
    return ProxyNode(protocol="http", address=host, port=port,
                     id_or_password=username, encryption=password,
                     security="tls" if is_https else "none",
                     sni=sni if is_https else None,
                     remarks=remarks or ("HTTPS Node" if is_https else "HTTP Node"))


def parse_link(share_link: str) -> ProxyNode:
    """Parse a single proxy share link (upstream ProxyParserService.parseLink)."""
    trimmed = share_link.strip()
    if not trimmed:
        raise ValueError("Share link cannot be empty")
    if trimmed.startswith("vless://"):
        return _parse_vless(trimmed)
    if trimmed.startswith("vmess://"):
        return _parse_vmess(trimmed)
    if trimmed.startswith("trojan://"):
        return _parse_trojan(trimmed)
    if trimmed.startswith("ss://"):
        return _parse_shadowsocks(trimmed)
    if trimmed.startswith("socks://") or trimmed.startswith("socks5://"):
        return _parse_socks(trimmed)
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        return _parse_http(trimmed)
    raise ValueError(
        "Unsupported proxy link protocol. Supported protocols: vless://, vmess://, "
        "trojan://, ss://, socks://, socks5://, http://, https://")


def generate_chain_profile(node_share_links: list[str],
                           socks_port: int = 10808,
                           http_port: int = 10809) -> dict:
    """Generate the chained multi-hop Xray profile JSON (upstream generateChainProfile)."""
    if len(node_share_links) < 2:
        raise ValueError("At least 2 nodes (Entry and Exit) are required for chaining.")

    parsed_nodes: list[ProxyNode] = []
    for index, link in enumerate(node_share_links):
        try:
            parsed_nodes.append(parse_link(link))
        except ValueError as exc:
            raise ValueError(f"Failed to parse Hop {index}: {exc}") from exc

    outbounds: list[dict] = []
    for index, node in enumerate(parsed_nodes):
        tag = f"hop{index}"
        dialer = f"hop{index - 1}" if index > 0 else None
        outbounds.append(node.to_xray_outbound(tag, dialer))
    outbounds.append({"tag": "direct", "protocol": "freedom", "settings": {}})
    outbounds.append({"tag": "block", "protocol": "blackhole", "settings": {}})

    final_hop_tag = f"hop{len(parsed_nodes) - 1}"
    entry = parsed_nodes[0].protocol.upper()
    exit_ = parsed_nodes[-1].protocol.upper()
    remarks = f"Chained: {entry} (Entry) \u2192 {exit_} (Exit)"

    profile = {
        "remarks": remarks,
        "log": {"loglevel": "warning"},
        "inbounds": [
            {"tag": "socks-in", "port": socks_port, "listen": "127.0.0.1",
             "protocol": "socks", "settings": {"udp": True, "auth": "noauth"}},
            {"tag": "http-in", "port": http_port, "listen": "127.0.0.1",
             "protocol": "http", "settings": {}},
        ],
        "outbounds": outbounds,
        "routing": {"rules": [{"type": "field", "outboundTag": final_hop_tag,
                               "port": "0-65535"}]},
    }
    return profile


def generate_chain(links: str, socks_port: int = 10808, http_port: int = 10809) -> dict:
    """Generate a chained profile from newline-separated proxy links."""
    node_links = [line.strip() for line in links.splitlines() if line.strip()]
    if len(node_links) < 2:
        return {"ok": False,
                "error": "Please provide at least 2 valid proxy links (Entry and Exit).",
                "profile": None}
    try:
        profile = generate_chain_profile(node_links, socks_port, http_port)
        return {"ok": True, "error": None, "profile": profile,
                "json": json.dumps(profile, indent=2), "hop_count": len(node_links)}
    except ValueError as exc:
        return {"ok": False, "error": str(exc), "profile": None}