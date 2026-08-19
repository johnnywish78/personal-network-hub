"""Cloudflare Fix (Network Checker) — VLESS → Xray JSON transform.

Ported from the upstream cloudflare_fix_service.dart (GPL-3.0
mirarr-app/network-checker). Turns a VLESS+TLS+WS or VLESS+TLS+xHTTP share
link into a Cloudflare-optimized Xray JSON configuration. Pure string/config
transformation - no network access.
"""

from __future__ import annotations

import json
import urllib.parse

from . import common

DEFAULT_CIPHER_SUITES = (
    "TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_128_GCM_SHA256:"
    "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384:TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384:"
    "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256:TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256:"
    "TLS_ECDHE_ECDSA_WITH_CHACHA20_POLY1305_SHA256:TLS_ECDHE_RSA_WITH_CHACHA20_POLY1305_SHA256:"
    "TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA:TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA:"
    "TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA256:TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA256"
)

DEFAULT_DNS_SERVER = "https://cloudflare-dns.com/dns-query"

DEFAULT_DNS_HOSTS = {
    "domain:googleapis.cn": "googleapis.com",
    "dns.alidns.com": ["223.5.5.5", "223.6.6.6", "2400:3200::1", "2400:3200:baba::1"],
    "dns.sse.cisco.com": ["208.67.220.220", "208.67.222.222",
                          "2620:119:35::35", "2620:119:53::53"],
    "dns.umbrella.com": ["208.67.220.220", "208.67.222.222",
                         "2620:119:35::35", "2620:119:53::53"],
    "one.one.one.one": ["1.1.1.1", "1.0.0.1", "2606:4700:4700::1111", "2606:4700:4700::1001"],
    "1dot1dot1dot1.cloudflare-dns.com": ["1.1.1.1", "1.0.0.1",
                                         "2606:4700:4700::1111", "2606:4700:4700::1001"],
    "dns.cloudflare.com": ["162.159.61.8", "172.64.41.8", "2a06:98c1:52::8", "2803:f800:53::8"],
    "cloudflare-dns.com": ["104.16.248.249", "104.16.249.249",
                           "2606:4700::6810:f8f9", "2606:4700::6810:f9f9"],
    "engage.cloudflareclient.com": ["162.159.192.1", "2606:4700:d0::a29f:c001"],
    "doh.pub": ["1.12.12.12", "120.53.53.53"],
    "dot.pub": ["1.12.12.12", "120.53.53.53"],
    "dns.google": ["8.8.8.8", "8.8.4.4", "2001:4860:4860::8888", "2001:4860:4860::8844"],
    "dns.quad9.net": ["9.9.9.9", "149.112.112.112", "2620:fe::fe", "2620:fe::9"],
    "dns.sb": ["45.11.45.11", "185.222.222.222", "2a09::", "2a11::"],
    "common.dot.dns.yandex.net": ["77.88.8.8", "77.88.8.1",
                                  "2a02:6b8::feed:0ff", "2a02:6b8:0:1::feed:0ff"],
}

AVAILABLE_FINGERPRINTS = ["unsafe", "chrome", "firefox", "android", "randomized",
                          "random", "edge", "safari", "360", "qq", "ios"]


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


def _split_csv(text: str) -> list[str]:
    return [s.strip() for s in text.split(",") if s.strip()]


class CloudflareFixResult:
    def __init__(self, json_config: dict, formatted_json: str, remarks: str,
                 address: str, port: int, network: str, sni: str,
                 fingerprint: str, alpn: list[str]):
        self.json_config = json_config
        self.formatted_json = formatted_json
        self.remarks = remarks
        self.address = address
        self.port = port
        self.network = network
        self.sni = sni
        self.fingerprint = fingerprint
        self.alpn = alpn

    def to_dict(self) -> dict:
        return {
            "json_config": self.json_config,
            "formatted_json": self.formatted_json,
            "remarks": self.remarks,
            "address": self.address,
            "port": self.port,
            "network": self.network,
            "sni": self.sni,
            "fingerprint": self.fingerprint,
            "alpn": self.alpn,
        }


def transform_vless_url(
    share_link: str,
    socks_port: int = 10808,
    http_port: int = 10809,
    dns_server: str = DEFAULT_DNS_SERVER,
    remark_suffix: str = "-custom",
    fingerprint: str = "unsafe",
    alpn: list[str] | None = None,
    cipher_suites: str = DEFAULT_CIPHER_SUITES,
    enable_finalmask: bool = True,
    frag1_packets: str = "tlshello",
    frag1_lengths: list[str] | None = None,
    frag1_delays: list[str] | None = None,
    frag1_max_split: str = "0",
    frag2_packets: str = "1-1",
    frag2_lengths: list[str] | None = None,
    frag2_delays: list[str] | None = None,
    frag2_max_split: str = "355",
) -> CloudflareFixResult:
    """Transform a VLESS share link into a Cloudflare Fix Xray JSON config.

    Strictly requires security=tls and network type ws or xhttp (or splithttp,
    normalized to xhttp) - mirroring upstream.
    """
    trimmed = share_link.strip()
    if not trimmed:
        raise ValueError("VLESS configuration link cannot be empty.")
    if not trimmed.startswith("vless://"):
        raise ValueError('Invalid protocol. Only VLESS links starting with "vless://" are supported.')

    uri_part, _, fragment = trimmed[8:].partition("#")
    raw_remarks = urllib.parse.unquote(fragment) if fragment else "VLESS Node"
    main_part, _, query_string = uri_part.partition("?")
    uuid, _, host_port = main_part.partition("@")
    if not uuid or not host_port:
        raise ValueError('Invalid VLESS link format: missing "@" separating UUID and server address.')

    last_colon = host_port.rfind(":")
    if last_colon == -1:
        raise ValueError(f"Invalid address/port in VLESS link: {host_port}")
    address = host_port[:last_colon]
    try:
        port = int(host_port[last_colon + 1:])
    except ValueError as exc:
        raise ValueError(f"Invalid port number: {host_port[last_colon + 1:]}") from exc
    if not (0 < port <= 65535):
        raise ValueError(f"Invalid port number: {port}")

    params = _parse_query_string(query_string)
    security = (params.get("security") or params.get("tls") or "none").lower()
    network = (params.get("type") or params.get("network") or "tcp").lower()

    if security != "tls" or network not in ("ws", "xhttp", "splithttp"):
        raise ValueError("Only VLESS+TLS+WS and VLESS+TLS+xHTTP configurations are supported.")

    normalized_network = "xhttp" if network in ("xhttp", "splithttp") else "ws"
    sni = params.get("sni") or params.get("peer") or params.get("host") or address
    path = urllib.parse.unquote(params.get("path") or "")
    host = params.get("host") or ""
    flow = params.get("flow") or ""
    encryption = (params.get("encryption") or "none") or "none"
    mode = params.get("mode") or "auto"
    final_remarks = raw_remarks if raw_remarks.endswith(remark_suffix) else raw_remarks + remark_suffix

    alpn_list = alpn if alpn is not None else ["http/1.1"]
    frag1_lengths = frag1_lengths if frag1_lengths else ["5", "94", "1"]
    frag1_delays = frag1_delays if frag1_delays else ["0"]
    frag2_lengths = frag2_lengths if frag2_lengths else ["109", "1"]
    frag2_delays = frag2_delays if frag2_delays else ["1"]

    stream_settings: dict = {
        "network": normalized_network,
        "security": "tls",
        "sockopt": {
            "domainStrategy": "UseIP",
            "happyEyeballs": {
                "interleave": 2,
                "maxConcurrentTry": 4,
                "prioritizeIPv6": False,
                "tryDelayMs": 250,
            },
        },
        "tlsSettings": {
            "allowInsecure": False,
            "alpn": alpn_list,
            "cipherSuites": cipher_suites if cipher_suites else DEFAULT_CIPHER_SUITES,
            "fingerprint": fingerprint,
            "serverName": sni,
        },
    }
    if enable_finalmask:
        stream_settings["finalmask"] = {
            "tcp": [
                {"type": "fragment",
                 "settings": {"packets": frag1_packets, "lengths": frag1_lengths,
                              "delays": frag1_delays, "maxSplit": frag1_max_split}},
                {"type": "fragment",
                 "settings": {"packets": frag2_packets, "lengths": frag2_lengths,
                              "delays": frag2_delays, "maxSplit": frag2_max_split}},
            ]
        }
    if normalized_network == "ws":
        stream_settings["wsSettings"] = {"host": host if host else sni, "path": path}
    else:
        stream_settings["xhttpSettings"] = {
            "host": host if host else sni, "path": path, "mode": mode}

    json_config = {
        "dns": {"hosts": DEFAULT_DNS_HOSTS, "servers": [dns_server], "tag": "dns-module"},
        "inbounds": [
            {"listen": "127.0.0.1", "port": socks_port, "protocol": "socks",
             "settings": {"auth": "noauth", "udp": True, "userLevel": 8},
             "sniffing": {"destOverride": ["http", "tls", "quic"], "enabled": True,
                          "routeOnly": False},
             "tag": "socks"},
            {"listen": "127.0.0.1", "port": http_port, "protocol": "http",
             "settings": {"userLevel": 8},
             "sniffing": {"destOverride": ["http", "tls", "quic"], "enabled": True,
                          "routeOnly": False},
             "tag": "http"},
        ],
        "log": {"loglevel": "warning"},
        "outbounds": [
            {"mux": {"concurrency": -1, "enabled": False}, "protocol": "vless",
             "settings": {"address": address, "encryption": encryption, "flow": flow,
                          "id": uuid, "level": 8, "port": port},
             "streamSettings": stream_settings, "tag": "proxy"},
            {"protocol": "freedom",
             "streamSettings": {"network": "tcp",
                                "sockopt": {"domainStrategy": "UseIP"}},
             "tag": "direct"},
            {"protocol": "blackhole", "settings": {}, "tag": "block"},
        ],
        "remarks": final_remarks,
        "routing": {"domainStrategy": "AsIs",
                    "rules": [{"inboundTag": ["dns-module"], "outboundTag": "proxy",
                               "type": "field"}]},
    }

    return CloudflareFixResult(
        json_config=json_config,
        formatted_json=json.dumps(json_config, indent=2),
        remarks=final_remarks,
        address=address,
        port=port,
        network=normalized_network.upper(),
        sni=sni,
        fingerprint=fingerprint,
        alpn=alpn_list,
    )


def transform_vless_lines(links: str, **options) -> dict:
    """Transform multiple VLESS links, one per line. Returns per-link results."""
    results = []
    errors = []
    for line in links.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            results.append(transform_vless_url(line, **options).to_dict())
        except ValueError as exc:
            errors.append({"link": line, "error": str(exc)})
    return {"total": len(results), "results": results, "errors": errors}