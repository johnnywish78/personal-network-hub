#!/usr/bin/env python3
"""Convert upstream Network Checker (Dart) data files into JSON assets.

Reads from third_party/network-checker/lib and writes JSON files under
backend/network/checker/data/. Re-run whenever the vendored app is updated.

Attribution: data originated from the GPL-3.0 mirarr-app/network-checker project.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "third_party" / "network-checker" / "lib"
OUT = ROOT / "backend" / "network" / "checker" / "data"


def extract_string_list(path: Path, name: str) -> list[str]:
    """Extract a `const List<String> name = [...]` into a list of strings."""
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"const List<String> {name} = \[(.*?)\];", text, re.S)
    if not match:
        raise SystemExit(f"const List<String> {name} not found in {path}")
    return re.findall(r"'([^']*)'", match.group(1))


def extract_raw_string(path: Path, name: str) -> str:
    """Extract a `const String name = r'''...'''` raw block."""
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"const String {name} = r'''(.+?)'''", text, re.S)
    if not match:
        raise SystemExit(f"const String {name} not found in {path}")
    return match.group(1).strip()


def _split_top_level(s: str, sep: str = ",") -> list[str]:
    """Split on `sep` outside quotes and brackets."""
    parts, depth, quote_char = [], 0, None
    start = 0
    i = 0
    while i < len(s):
        ch = s[i]
        if quote_char is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote_char:
                quote_char = None
        elif ch in "'\"":
            quote_char = ch
        elif ch in "[({":
            depth += 1
        elif ch in "])}":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(s[start:i])
            start = i + 1
        i += 1
    parts.append(s[start:])
    return [p.strip() for p in parts if p.strip()]


def _parse_value(value: str):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        return re.findall(r"['\"]([^'\"]*)['\"]", value)
    if len(value) >= 2 and value[0] in "'\"" and value[-1] == value[0]:
        return value[1:-1]
    return value


def extract_object_list(path: Path, cls_name: str) -> list[dict]:
    """Extract `const List<X> name = [ X(...), ... ]` objects with named fields.

    Only matches object constructions inside the const list body (not the
    class's own `const X({...})` constructor).
    """
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"const List<{cls_name}> \w+ = \[(.*?)\];", text, re.S)
    if not match:
        raise SystemExit(f"const List<{cls_name}> not found in {path}")
    body = match.group(1)

    result = []
    for obj_match in re.finditer(rf"{cls_name}\((.*?)\)\s*,", body, re.S):
        obj: dict = {}
        for arg in _split_top_level(obj_match.group(1)):
            key, _, value = arg.partition(":")
            if not value.strip():
                continue
            obj[key.strip()] = _parse_value(value)
        result.append(obj)
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # --- Flat IP lists (from core/services/cdn_ips.dart) ------------------
    cdn = UPSTREAM / "core" / "services" / "cdn_ips.dart"
    for name in ("cloudflareIps", "akamaiIps", "azureIps", "cloudfrontIps", "fastlyIps", "googleIps"):
        (OUT / f"{name}.json").write_text(
            json.dumps(extract_string_list(cdn, name), indent=1), encoding="utf-8"
        )
        print(f"wrote {name}.json")

    # --- Akamai scanner default CIDR ranges ------------------------------
    akamai = UPSTREAM / "features" / "akamai_scan" / "data" / "akamai_ip_ranges.dart"
    raw = extract_raw_string(akamai, "akamaiIpRanges")
    cidrs = [line.strip() for line in raw.splitlines() if line.strip() and not line.startswith("#")]
    (OUT / "akamai_ip_ranges.json").write_text(json.dumps(cidrs, indent=1), encoding="utf-8")
    print("wrote akamai_ip_ranges.json")

    # --- DNS providers (dns latency test) ---------------------------------
    dns_prov = UPSTREAM / "features" / "dns_scanner" / "data" / "dns_providers.dart"
    (OUT / "dns_providers.json").write_text(
        json.dumps(extract_object_list(dns_prov, "DnsProvider"), indent=1), encoding="utf-8"
    )
    print("wrote dns_providers.json")

    # --- Top domains (domain checker default) ------------------------------
    top = UPSTREAM / "features" / "domain_checker" / "data" / "top_domains.dart"
    (OUT / "top_domains.json").write_text(
        json.dumps(extract_string_list(top, "topDomains"), indent=1), encoding="utf-8"
    )
    print("wrote top_domains.json")

    # --- DNS hunter ranges --------------------------------------------------
    ranges = UPSTREAM / "features" / "dns_hunter" / "data" / "dns_ranges.dart"
    (OUT / "dns_ranges.json").write_text(
        json.dumps(extract_object_list(ranges, "DnsRangeProvider"), indent=1), encoding="utf-8"
    )
    print("wrote dns_ranges.json")

    # --- Netlify generator predefined values --------------------------------
    netlify = UPSTREAM / "features" / "netlify_generator" / "data" / "predefined_values.dart"
    (OUT / "netlify_predefined.json").write_text(
        json.dumps(
            {
                "predefinedSnis": extract_string_list(netlify, "predefinedSnis"),
                "predefinedIps": extract_string_list(netlify, "predefinedIps"),
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print("wrote netlify_predefined.json")

    # --- Edge IP checker default Cloudflare CIDR ranges ---------------------
    edge = UPSTREAM / "features" / "edge_ip_checker" / "cf_ip_ranges.dart"
    raw = extract_raw_string(edge, "cloudflareIpRanges")
    cidrs = [line.strip() for line in raw.splitlines() if line.strip() and not line.startswith("#")]
    (OUT / "edge_ip_ranges.json").write_text(json.dumps(cidrs, indent=1), encoding="utf-8")
    print("wrote edge_ip_ranges.json")

    print("\nDone.")


if __name__ == "__main__":
    main()
