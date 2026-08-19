"""Config generation tools: VLESS config modifier and Netlify generator.

Ported from upstream vless_config_modifier_controller.dart and
netlify_generator_controller.dart. Pure string/config manipulation - no
network access.
"""

from __future__ import annotations

import urllib.parse

from . import common


def parse_vless_configs(text: str) -> list[dict]:
    """Parse `vless://uuid@host:port?query#fragment` lines."""
    configs: list[dict] = []
    for line in text.splitlines():
        trimmed = line.strip()
        if not trimmed.startswith("vless://"):
            continue
        try:
            without_prefix = trimmed[8:]
            before_fragment, _, fragment = without_prefix.partition("#")
            before_query, _, query_string = before_fragment.partition("?")
            uuid, _, host_port = before_query.partition("@")
            if not uuid or not host_port:
                continue
            host, sep, port_str = host_port.rpartition(":")
            if not sep:
                continue
            try:
                port = int(port_str)
            except ValueError:
                continue
            configs.append({"uuid": uuid, "host": host, "port": port,
                            "query_string": query_string, "fragment": fragment})
        except Exception:  # noqa: BLE001 - skip invalid lines like upstream
            continue
    return configs


def parse_ips_verbose(text: str) -> list[str]:
    """Expand CIDRs, hyphen IP ranges, and single IPs (upstream _parseIpsIsolate)."""
    ips: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "/" in line:
            ips.extend(common.expand_cidr_limits(line))
        elif "-" in line:
            start, sep, end = line.partition("-")
            if sep:
                ips.extend(common.expand_ip_range(start.strip(), end.strip()))
        else:
            ips.append(line)
    return ips


def _split_target_ip(value: str, default_port: int) -> tuple[str, int]:
    first_colon = value.find(":")
    last_colon = value.rfind(":")
    has_multiple = first_colon != last_colon
    has_brackets = value.startswith("[") and "]" in value
    if last_colon != -1 and (not has_multiple or has_brackets):
        ip_part, _, port_str = value.rpartition(":")
        try:
            parsed = int(port_str)
            if 0 < parsed <= 65535:
                return ip_part, parsed
        except ValueError:
            pass
    return value, default_port


def modify_vless_configs(configs_text: str, ips_text: str,
                         parse_ips: bool = True) -> dict:
    """Generate config/IP combinations (upstream _generateConfigsIsolate)."""
    parsed = parse_vless_configs(configs_text)
    if not parsed:
        return {"error": 'No valid VLESS configs found. Make sure they start with "vless://"',
                "configs": []}
    ips = parse_ips_verbose(ips_text) if parse_ips else \
        [line.strip() for line in ips_text.splitlines() if line.strip()]
    if not ips:
        return {"error": "No valid IPs found. Enter one IP per line.", "configs": []}

    generated: list[str] = []
    for config in parsed:
        for ip in ips:
            target_ip, target_port = _split_target_ip(ip, config["port"])
            generated.append(
                f"vless://{config['uuid']}@{target_ip}:{target_port}?{config['query_string']}#{config['fragment']}"
            )
    return {
        "parsed_configs": parsed,
        "ip_count": len(ips),
        "total_generated": len(generated),
        "configs": generated,
    }


def generate_netlify_configs(uuid: str, path: str, netlify_domain: str, xhttp_object: str,
                             snis: list[str], ips: list[str]) -> dict:
    """Generate Netlify vless configs (upstream _generateNetlifyConfigsIsolate)."""
    encoded_path = urllib.parse.quote(path)
    encoded_extra = urllib.parse.quote(xhttp_object)
    generated: list[str] = []
    for ip in ips:
        for sni in snis:
            generated.append(
                f"vless://{uuid}@{ip}:443"
                f"?encryption=none"
                f"&security=tls"
                f"&sni={sni}"
                f"&fp=chrome"
                f"&alpn=h2%2Chttp%2F1.1"
                f"&insecure=1"
                f"&allowInsecure=1"
                f"&type=xhttp"
                f"&host={netlify_domain}"
                f"&path={encoded_path}"
                f"&mode=auto"
                f"&extra={encoded_extra}"
                f"#Netlify"
            )
    return {"total_generated": len(generated), "configs": generated}