"""Internet Diagnostics suite (Network Checker).

Ported from upstream internet_diagnostics_service.dart. Runs a battery of
network checks and returns structured, human-readable results.
"""

from __future__ import annotations

import json
import random
import socket
import ssl
import struct
import time

import httpx

from . import common
from .data import cloudflare_ips as _cloudflare_ips
from .data import akamai_ips as _akamai_ips

TIMEOUT = 3.0
DNS_ANALYSIS_TIMEOUT = 2.0
_DNS_ANALYSIS_DOMAINS = ["google.com", "cloudflare.com", "github.com", "wikipedia.org"]
_KNOWN_HIJACK_IPS = {"127.0.0.1", "0.0.0.0", "10.10.34.34"}

_DNS_ANALYSIS_PROVIDERS = [
    {"name": "ISP DNS", "address": None, "uses_system_resolver": True},
    {"name": "Google DNS", "address": "8.8.8.8"},
    {"name": "Cloudflare DNS", "address": "1.1.1.1"},
    {"name": "Quad9 DNS", "address": "9.9.9.9"},
    {"name": "OpenDNS", "address": "208.67.222.222"},
]

_TLS_TARGETS = [
    ("chatgpt.com", "188.114.98.0"), ("vercel.com", "198.169.1.1"),
    ("static.cloudflareinsights.com", "104.16.80.73"), ("sourceforge.net", "104.18.13.149"),
    ("dash.cloudflare.com", "104.17.111.184"), ("a.fsdn.com", "104.18.17.56"),
    ("npmjs.com", "104.17.134.117"), ("e7.c.lencr.org", "104.18.20.213"),
    ("cdnjs.com", "104.24.196.20"), ("creativecommons.org", "104.20.6.134"),
    ("nodejs.org", "104.16.213.131"), ("medium.com", "162.159.152.4"),
    ("jsdelivr.com", "188.114.98.0"), ("phpbb.com", "104.18.19.20"),
    ("codepen.io", "104.16.147.32"), ("google.com", "216.239.38.120"),
    ("translate.google.com", "172.217.168.78"), ("gmail.com", "142.251.20.18"),
    ("github.com", "140.82.121.3"), ("www.speedtest.net", "104.17.147.22"),
    ("coingecko.cfd", "8.6.112.0"), ("store.steampowered.com", "2.23.168.78"),
    ("apple.com", "17.253.144.10"), ("chat.deepseek.com", "3.173.21.63"),
    ("wikipedia.org", "185.15.59.224"), ("play.google.com", "142.251.20.138"),
    ("whatsapp.com", "57.144.245.32"), ("playstation.com", "52.8.87.150"),
    ("xbox.com", "20.76.201.171"), ("microsoft.com", "13.107.226.45"),
    ("fastly.com", "151.101.193.57"), ("www.hcaptcha.com", "104.19.229.21"),
    ("sciencedirect.com", "203.22.241.9"), ("code.visualstudio.com", "13.107.253.45"),
    ("crelease-assets.githubusercontent.com", "185.199.110.133"),
]

TARGET_WEBSITES = [
    {"name": "Google", "domain": "www.google.com"},
    {"name": "YouTube", "domain": "www.youtube.com"},
    {"name": "GitHub", "domain": "github.com"},
    {"name": "Wikipedia", "domain": "wikipedia.org"},
    {"name": "Reddit", "domain": "www.reddit.com"},
    {"name": "Stack Overflow", "domain": "stackoverflow.com"},
    {"name": "ChatGPT", "domain": "chatgpt.com"},
    {"name": "Claude", "domain": "claude.ai"},
    {"name": "Gemini", "domain": "gemini.google.com"},
]

TARGET_SOCIAL_MEDIA = [
    {"name": "Telegram", "primary": "telegram.org", "secondary": "api.telegram.org"},
    {"name": "WhatsApp", "primary": "web.whatsapp.com", "secondary": "graph.whatsapp.com"},
    {"name": "Discord", "primary": "discord.com", "secondary": "gateway.discord.gg"},
    {"name": "Instagram", "primary": "instagram.com", "secondary": "scontent.cdninstagram.com"},
    {"name": "X (Twitter)", "primary": "x.com", "secondary": "api.x.com"},
    {"name": "Facebook", "primary": "facebook.com", "secondary": "graph.facebook.com"},
    {"name": "YouTube", "primary": "youtube.com", "secondary": "i.ytimg.com"},
]

TARGET_CDNS = [
    ("Cloudflare", "cloudflare.com", _cloudflare_ips),
    ("Akamai", "akamai.com", _akamai_ips),
]

PROTOCOL_DOMAINS = {
    "TCP HTTP": (["google.com", "cloudflare.com", "wikipedia.org", "github.com"], "Plain HTTP connectivity on TCP port 80"),
    "TCP HTTPS": (["google.com", "cloudflare.com", "wikipedia.org", "github.com"], "Secure HTTPS connectivity on TCP port 443"),
    "UDP Connectivity": (["dns.google", "one.one.one.one", "time.google.com", "time.windows.com"], "Generic UDP traffic via NTP and DNS"),
    "DNS-over-HTTPS": (["dns.google", "cloudflare-dns.com", "dns.quad9.net"], "DNS queries routed securely inside HTTPS request"),
    "DNS-over-TLS": (["dns.google", "one.one.one.one", "dns.quad9.net"], "DNS queries secured in TLS on port 853"),
    "ICMP Ping": (["google.com", "cloudflare.com", "github.com", "wikipedia.org"], "Standard ICMP Echo ping reachability"),
}


def check_dns_resolution() -> dict:
    targets = ["one.one.one.one", "dns.google"]
    start = time.monotonic()
    results = []
    for host in targets:
        t = time.monotonic()
        try:
            ips = sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
            results.append({"host": host, "success": bool(ips), "ips": ips,
                            "latency_ms": round((time.monotonic() - t) * 1000, 1), "error": None})
        except OSError as exc:
            results.append({"host": host, "success": False, "ips": [], "latency_ms": None,
                            "error": str(exc)})
    successful = [r for r in results if r["success"]]
    details = "\n".join(
        f"{'✓' if r['success'] else '✗'} {r['host']} - "
        f"{'Resolved successfully (' + str(r['latency_ms']) + 'ms) IPs: ' + ', '.join(r['ips']) if r['success'] else 'Failed (' + (r['error'] or '') + ')'}"
        for r in results)
    return {
        "name": "DNS Resolution",
        "success": bool(successful),
        "message": f"DNS resolution is available ({len(successful)} of {len(results)} endpoints succeeded)" if successful else "DNS resolution failed (all endpoints failed)",
        "latency_ms": min((r["latency_ms"] for r in successful), default=round((time.monotonic() - start) * 1000, 1)),
        "details": details,
    }


def _format_conn_error(exc: BaseException, timeout: float) -> str:
    message = str(exc).lower()
    if isinstance(exc, socket.timeout) or "timed out" in message:
        return f"Connection timed out after {timeout}s"
    if "connection refused" in message:
        return "Connection refused"
    if "network is unreachable" in message:
        return "Network is unreachable"
    if "no route to host" in message:
        return "No route to host"
    return f"Socket error: {exc}"


def _socket_connect_test(address: str, port: int, timeout: float = TIMEOUT) -> dict:
    start = time.monotonic()
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((address, port))
        local = sock.getsockname()
        latency = round((time.monotonic() - start) * 1000, 1)
        return {"success": True, "latency_ms": latency, "local": str(local[0]), "error": None}
    except (socket.timeout, OSError) as exc:
        return {"success": False, "latency_ms": None, "local": None,
                "error": _format_conn_error(exc, timeout)}
    finally:
        sock.close()


def check_ipv4_connectivity() -> dict:
    targets = [("Cloudflare DNS", "1.1.1.1", 53), ("Google DNS", "8.8.8.8", 53),
               ("Quad9 DNS", "9.9.9.9", 53)]
    results = []
    for name, address, port in targets:
        r = _socket_connect_test(address, port)
        results.append({"name": name, "address": address, "port": port, **r})
    successful = [r for r in results if r["success"]]
    details = "\n".join(
        f"{'✓' if r['success'] else '✗'} {r['name']} ({r['address']}:{r['port']}) - "
        f"{'Succeeded (' + str(r['latency_ms']) + 'ms)' if r['success'] else 'Failed (' + (r['error'] or '') + ')'}"
        for r in results)
    return {
        "name": "IPv4 Connectivity",
        "success": bool(successful),
        "message": f"IPv4 Internet access is available ({len(successful)} of {len(results)} endpoints reached)" if successful else "IPv4 connectivity unavailable (all endpoints failed)",
        "latency_ms": min((r["latency_ms"] for r in successful), default=None),
        "details": details,
    }


def check_ipv6_connectivity() -> dict:
    targets = [("Cloudflare IPv6 DNS", "2606:4700:4700::1111", 53),
               ("Google IPv6 DNS", "2001:4860:4860::8888", 53),
               ("Quad9 IPv6 DNS", "2620:fe::fe", 53)]
    results = []
    for name, address, port in targets:
        r = _socket_connect_test(address, port)
        results.append({"name": name, "address": address, "port": port, **r})
    successful = [r for r in results if r["success"]]
    details = "\n".join(
        f"{'✓' if r['success'] else '✗'} {r['name']} ([{r['address']}]:{r['port']}) - "
        f"{'Succeeded (' + str(r['latency_ms']) + 'ms)' if r['success'] else 'Failed (' + (r['error'] or '') + ')'}"
        for r in results)
    return {
        "name": "IPv6 Connectivity",
        "success": bool(successful),
        "message": f"IPv6 Internet access is available ({len(successful)} of {len(results)} endpoints reached)" if successful else "IPv6 connectivity unavailable (all endpoints failed)",
        "latency_ms": min((r["latency_ms"] for r in successful), default=None),
        "details": details,
    }


def check_https_traffic() -> dict:
    targets = ["https://www.cloudflare.com", "https://www.google.com"]
    results = []
    for url in targets:
        start = time.monotonic()
        try:
            with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
                response = client.head(url)
            results.append({"url": url, "success": response.status_code < 400,
                            "status_code": response.status_code,
                            "latency_ms": round((time.monotonic() - start) * 1000, 1)})
        except Exception as exc:  # noqa: BLE001
            results.append({"url": url, "success": False, "status_code": None,
                            "latency_ms": None, "error": str(exc)})
    successful = [r for r in results if r["success"]]
    details = "\n".join(
        f"{'✓' if r['success'] else '✗'} {r['url']} - "
        f"{'Succeeded (Status: ' + str(r['status_code']) + ', ' + str(r['latency_ms']) + 'ms)' if r['success'] else 'Failed (' + str(r.get('error') or ('Status: ' + str(r['status_code']))) + ')'}"
        for r in results)
    return {
        "name": "HTTPS Traffic",
        "success": bool(successful),
        "message": f"HTTPS traffic is available ({len(successful)} of {len(results)} endpoints succeeded)" if successful else "HTTPS handshake or query failed (all endpoints failed)",
        "latency_ms": min((r["latency_ms"] for r in successful), default=None),
        "details": details,
    }


# --- DNS provider analysis -------------------------------------------------

def _detect_suspicious_dns_answers(domain: str, ips: list[str], expect_nxdomain: bool,
                                   is_nxdomain: bool, rcode: int | None = None) -> list[str]:
    reasons: list[str] = []
    if expect_nxdomain:
        if not is_nxdomain and ips:
            reasons.append("NXDOMAIN hijacking: nonexistent domain returned IPs.")
        elif not is_nxdomain and rcode is not None and rcode != 3:
            reasons.append(f"Expected NXDOMAIN but received DNS RCODE {rcode}.")
        return reasons
    if is_nxdomain:
        reasons.append("Incorrect response: valid domain returned NXDOMAIN.")
    if not ips:
        reasons.append("No A records returned.")
    for ip in ips:
        if ip in _KNOWN_HIJACK_IPS or common.is_private_or_reserved_ipv4(ip):
            reasons.append(f"Suspicious answer for {domain}: {ip}.")
    return reasons


def _analyze_single_dns_provider(provider: dict, test_domains: list[str],
                                 nonexistent_domain: str) -> dict:
    query_results = []
    for domain in test_domains:
        query_results.append(_query_dns_provider(provider, domain, expect_nxdomain=False))
    query_results.append(_query_dns_provider(provider, nonexistent_domain, expect_nxdomain=True))

    successful = [q for q in query_results if q["success"]]
    latencies = [q["latency_ms"] for q in query_results if q["latency_ms"] is not None]
    return {
        "provider": provider,
        "query_results": query_results,
        "success_rate": round(len(successful) / len(query_results), 2) if query_results else 0.0,
        "average_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
    }


def _query_dns_provider(provider: dict, domain: str, expect_nxdomain: bool) -> dict:
    if provider.get("uses_system_resolver"):
        return _query_system_dns(domain, expect_nxdomain)
    return _query_udp_dns(provider["address"], domain, expect_nxdomain)


def _query_system_dns(domain: str, expect_nxdomain: bool) -> dict:
    start = time.monotonic()
    try:
        ips = sorted({info[4][0] for info in socket.getaddrinfo(domain, None)
                      if info[0] == socket.AF_INET})
        elapsed = round((time.monotonic() - start) * 1000, 1)
        reasons = _detect_suspicious_dns_answers(domain, ips, expect_nxdomain, False)
        return {"domain": domain, "success": not expect_nxdomain and bool(ips) and not reasons,
                "is_nxdomain": False, "ips": ips, "latency_ms": elapsed,
                "error": None, "suspicious_reasons": reasons}
    except socket.gaierror as exc:
        elapsed = round((time.monotonic() - start) * 1000, 1)
        message = str(exc).lower()
        is_nxdomain = "no address" in message or "nodename nor servname" in message
        reasons = _detect_suspicious_dns_answers(domain, [], expect_nxdomain, is_nxdomain)
        return {"domain": domain, "success": expect_nxdomain and is_nxdomain,
                "is_nxdomain": is_nxdomain, "ips": [], "latency_ms": elapsed,
                "error": None if is_nxdomain else message, "suspicious_reasons": reasons}
    except OSError as exc:
        elapsed = round((time.monotonic() - start) * 1000, 1)
        return {"domain": domain, "success": False, "is_nxdomain": False, "ips": [],
                "latency_ms": elapsed, "error": str(exc), "suspicious_reasons": []}


def _query_udp_dns(server: str, domain: str, expect_nxdomain: bool) -> dict:
    txn = random.randint(0, 0xFFFF)
    result = common.udp_dns_query(server, domain, DNS_ANALYSIS_TIMEOUT, txn=txn)
    if not result["success"] and result.get("rcode") is None:
        return {"domain": domain, "success": False, "is_nxdomain": False, "ips": [],
                "latency_ms": result["latency_ms"], "error": result["error"],
                "suspicious_reasons": []}
    reasons = _detect_suspicious_dns_answers(domain, result["ips"], expect_nxdomain,
                                             result.get("is_nxdomain", False), result.get("rcode"))
    rcode = result.get("rcode")
    success = (not expect_nxdomain and bool(result["ips"]) and not reasons) if rcode == 0 \
        else (expect_nxdomain and result.get("is_nxdomain", False))
    return {"domain": domain, "success": success,
            "is_nxdomain": result.get("is_nxdomain", False),
            "ips": result["ips"], "latency_ms": result["latency_ms"],
            "error": None if rcode in (0, 3) else f"DNS RCODE {rcode}",
            "suspicious_reasons": reasons}


def analyze_dns_providers() -> dict:
    nonexistent_domain = f"nx-{int(time.time() * 1000)}-{random.randint(0, 999999)}.invalid"
    provider_results = [_analyze_single_dns_provider(p, _DNS_ANALYSIS_DOMAINS, nonexistent_domain)
                        for p in _DNS_ANALYSIS_PROVIDERS]
    findings: list[str] = []
    consistency_by_domain: dict[str, float] = {}

    for domain in _DNS_ANALYSIS_DOMAINS:
        answer_sets: dict[str, int] = {}
        for pr in provider_results:
            query = next((q for q in pr["query_results"] if q["domain"] == domain), None)
            if query is None or not query["success"] or not query["ips"]:
                continue
            key = ",".join(query["ips"])
            answer_sets[key] = answer_sets.get(key, 0) + 1
        total = sum(answer_sets.values())
        if total == 0:
            consistency_by_domain[domain] = 0.0
            findings.append(f"No provider returned a valid answer for {domain}.")
            continue
        largest = max(answer_sets.values())
        consistency_by_domain[domain] = largest / total
        if len(answer_sets) > 1 and largest == 1 and total > 1:
            findings.append(f"All providers returned different A records for {domain}.")
        elif len(answer_sets) > 1:
            findings.append(f"Provider responses differ for {domain}.")

    nx_hijack = [pr["provider"]["name"] for pr in provider_results
                 if any("NXDOMAIN hijacking" in r for q in pr["query_results"]
                        for r in q["suspicious_reasons"])]
    if nx_hijack:
        findings.append(f"NXDOMAIN hijacking detected on {', '.join(nx_hijack)}.")
    for pr in provider_results:
        for q in pr["query_results"]:
            for reason in q["suspicious_reasons"]:
                findings.append(f"{pr['provider']['name']}: {reason}")

    latencies = [pr["average_latency_ms"] for pr in provider_results if pr["average_latency_ms"]]
    consistency = sum(consistency_by_domain.values()) / len(consistency_by_domain) \
        if consistency_by_domain else 0.0
    tampering = (len(nx_hijack) * 25
                 + sum(1 for pr in provider_results for q in pr["query_results"]
                       if q["suspicious_reasons"]) * 8
                 + round((1 - consistency) * 25)
                 + sum(1 for pr in provider_results if pr["success_rate"] < 0.5) * 10)
    tampering = max(0, min(100, tampering))
    successful_providers = sum(1 for pr in provider_results if pr["success_rate"] > 0)
    return {
        "name": "DNS Provider Analysis",
        "success": successful_providers > 0 and tampering < 70,
        "average_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "consistency_score": round(consistency, 2),
        "tampering_score": tampering,
        "findings": list(dict.fromkeys(findings)),
        "tested_domains": [*_DNS_ANALYSIS_DOMAINS, nonexistent_domain],
        "providers": provider_results,
    }


# --- Public IP / routing ---------------------------------------------------

def fetch_public_ip(domestic: bool) -> dict:
    name = "Domestic IP Query" if domestic else "International IP Query"
    start = time.monotonic()
    urls = ["https://chabokan.net/ip/"] if domestic else [
        "https://api.ipify.org", "https://icanhazip.com", "https://ident.me", "https://ifconfig.me/ip"]
    retrieved_ip: str | None = None
    resolved_url: str | None = None
    errors: list[str] = []
    for url in urls:
        if retrieved_ip:
            break
        try:
            with httpx.Client(timeout=8.0, follow_redirects=True) as client:
                response = client.get(url)
            if response.status_code == 200:
                body = response.text.strip()
                candidate = None
                if "chabokan.net" in url:
                    try:
                        data = response.json()
                        candidate = str(data.get("ipaddress") or data.get("ip") or "")
                    except (ValueError, json.JSONDecodeError):
                        candidate = None
                else:
                    candidate = body
                if candidate and common.is_valid_ipv4(candidate):
                    retrieved_ip = candidate
                    resolved_url = url
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Failed to query {url}: {exc}")

    elapsed = round((time.monotonic() - start) * 1000, 1)
    if retrieved_ip:
        geo = _fetch_geo_details(retrieved_ip)
        geo_details = (f"\nGeo Location: {geo.get('country_name', '?')}, {geo.get('city_name', '?')}"
                       f"\nISP/Network: {geo.get('isp_name', '?')}") if geo \
            else "\nGeo Location: Lookup failed or blocked"
        return {"name": name, "success": True, "message": f"IP retrieved: {retrieved_ip}",
                "latency_ms": elapsed,
                "details": f"API Source: {resolved_url}\nResolved IP: {retrieved_ip}{geo_details}\nTime taken: {elapsed}ms"}
    return {"name": name, "success": False, "message": "Failed to retrieve public IP",
            "latency_ms": elapsed, "details": "Attempted endpoints:\n" + "\n".join(errors)}


def _fetch_geo_details(ip: str) -> dict | None:
    try:
        with httpx.Client(timeout=3.0) as client:
            response = client.get(f"https://freeipapi.com/api/json/{ip}")
        if response.status_code == 200:
            data = response.json()
            return {
                "country_name": data.get("countryName") or data.get("country_name"),
                "city_name": data.get("cityName") or data.get("city_name"),
                "isp_name": data.get("isp") or data.get("ispName") or data.get("isp_name"),
            }
    except Exception:  # noqa: BLE001
        return None
    return None


def analyze_public_ips(domestic: dict, international: dict) -> dict:
    name = "IP Routing & Gateway Analysis"
    if not domestic["success"] and not international["success"]:
        return {"name": name, "success": False, "message": "Routing check failed - you are offline",
                "details": "Both domestic and international IP queries failed. Please check your physical connection."}
    if not domestic["success"]:
        return {"name": name, "success": False, "message": "Domestic gateway is unreachable",
                "details": "International endpoints are reachable, but domestic CDNs are blocked or unreachable.\nThis typically occurs if your VPN/Proxy is misconfigured."}
    if not international["success"]:
        return {"name": name, "success": False, "message": "International gateway is blocked",
                "details": "Domestic gateways resolved, but international IP servers are blocked.\nThis indicates severe international internet censorship."}
    domestic_ip = domestic["message"].replace("IP retrieved: ", "").strip()
    international_ip = international["message"].replace("IP retrieved: ", "").strip()
    if domestic_ip == international_ip:
        return {"name": name, "success": True, "message": "Direct Routing (Gateways Match)",
                "details": f"Domestic IP: {domestic_ip}\nInternational IP: {international_ip}\n\nRouting Status: MATCH\nBoth gateways egress from the exact same point."}
    return {"name": name, "success": True, "message": "Split Routing Detected (IP Mismatch)",
            "details": f"Domestic IP: {domestic_ip}\nInternational IP: {international_ip}\n\nRouting Status: MISMATCH / SPLIT TUNNEL\nA routing discrepancy is detected - split-tunneling or DPI/proxy."}


# --- TLS analysis ----------------------------------------------------------

def analyze_tls_targets(public_ip: str | None = None) -> dict:
    results = []
    for domain, expected_ip in _TLS_TARGETS:
        try:
            resolved = sorted({info[4][0] for info in socket.getaddrinfo(domain, None)
                               if info[0] == socket.AF_INET})[:5]
        except OSError:
            resolved = []
        handshake = common.tls_handshake(resolved[0], 443, domain, TIMEOUT) if resolved \
            else {"reachable": False, "error": "DNS resolution failed", "cert": None}
        cert = handshake.get("cert") or {}
        cert_valid = _cert_is_valid(cert)
        cert_mismatch = not _cert_looks_like_domain(cert, domain)
        resolution_mismatch = bool(resolved) and not _same_ipv4_c24(resolved, expected_ip)
        if handshake["reachable"]:
            findings = []
            if cert_mismatch:
                findings.append("certificate mismatch")
            if resolution_mismatch:
                findings.append("resolved IP differs from expected subnet")
            tampering = _score_tampering(False, cert_valid, cert_mismatch, resolution_mismatch,
                                         False, not bool(resolved))
        else:
            tampering = _score_tampering(True, False, False, resolution_mismatch, False, True)
        results.append({
            "domain": domain, "expected_ip": expected_ip, "resolved_ips": resolved,
            "handshake_success": handshake["reachable"],
            "handshake_latency_ms": handshake["latency_ms"],
            "certificate_valid": cert_valid, "certificate_mismatch": cert_mismatch,
            "resolution_mismatch": resolution_mismatch, "tampering_score": tampering,
            "error": handshake["error"],
        })

    successful = [r for r in results if r["handshake_success"]]
    valid_certs = [r for r in results if r["certificate_valid"]]
    mismatches = [r for r in results if r["certificate_mismatch"]]
    latencies = [r["handshake_latency_ms"] for r in results if r["handshake_latency_ms"]]
    avg_score = round(sum(r["tampering_score"] for r in results) / len(results)) if results else 100
    findings = []
    if mismatches:
        findings.append(f"{len(mismatches)} targets have possible certificate mismatch.")
    failed = len(results) - len(successful)
    if failed:
        findings.append(f"{failed} targets failed TLS handshake.")
    return {
        "name": "TLS / HTTPS Interception Analysis",
        "success": bool(successful) and avg_score < 70,
        "successful_handshakes": len(successful),
        "valid_certificates": len(valid_certs),
        "certificate_mismatches": len(mismatches),
        "average_handshake_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "average_tampering_score": avg_score,
        "findings": findings,
        "results": results,
    }


def _cert_is_valid(cert: dict) -> bool:
    if not cert:
        return False
    try:
        import datetime
        not_before = datetime.datetime.strptime(cert["notBefore"], "%b %d %H:%M:%S %Y %Z")
        not_after = datetime.datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
        now = datetime.datetime.utcnow()
        return not_before < now < not_after
    except (KeyError, ValueError):
        return False


def _cert_looks_like_domain(cert: dict, domain: str) -> bool:
    if not cert:
        return True
    subject = str(cert.get("subject", "")).lower()
    import re as _re
    match = _re.search(r"cn=([^,\n]+)", subject)
    if not match:
        return True
    return _domain_matches(match.group(1).strip(), domain)


def _domain_matches(name: str, domain: str) -> bool:
    name = name.lower()
    domain = domain.lower()
    if name == domain:
        return True
    if name.startswith("*."):
        suffix = name[1:]
        return domain.endswith(suffix) and len(domain.split(".")) == len(suffix.split("."))
    return False


def _same_ipv4_c24(resolved_ips: list[str], expected_ip: str) -> bool:
    parts = expected_ip.split(".")
    if len(parts) != 4:
        return False
    prefix = ".".join(parts[:3])
    return any(ip.split(".")[:3] == parts[:3] for ip in resolved_ips)


def _score_tampering(handshake_failed: bool, cert_valid: bool, cert_mismatch: bool,
                     resolution_mismatch: bool, trace_mismatch: bool, trace_unavailable: bool) -> int:
    score = 0
    if handshake_failed:
        score += 45
    if not cert_valid:
        score += 25
    if cert_mismatch:
        score += 35
    if resolution_mismatch:
        score += 12
    if trace_mismatch:
        score += 25
    if trace_unavailable:
        score += 8
    return max(0, min(100, score))


# --- Website / social / CDN reachability ------------------------------------

def test_website_reachability(name: str, domain: str) -> dict:
    start = time.monotonic()
    try:
        resolved = [info[4][0] for info in socket.getaddrinfo(domain, None) if info[0] == socket.AF_INET]
    except OSError as exc:
        return {"name": name, "domain": domain, "status": "dns_failure",
                "error_details": f"DNS resolution failed: {exc}"}
    if not resolved:
        return {"name": name, "domain": domain, "status": "dns_failure",
                "error_details": "DNS resolution completed but returned 0 IP addresses."}
    resolved_ip = resolved[0]
    if resolved_ip in ("127.0.0.1", "10.10.34.34"):
        return {"name": name, "domain": domain, "status": "blocked",
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "error_details": f"DNS hijacking detected! Resolved to known block IP: {resolved_ip}"}
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            response = client.head(f"https://{domain}")
        elapsed = round((time.monotonic() - start) * 1000, 1)
        note = (f"\n\nNote: Server returned HTTP status {response.status_code} (e.g., client/WAF rejection), "
                f"but routing and SSL/TLS handshake succeeded. The site is REACHABLE.") if response.status_code >= 400 else ""
        return {"name": name, "domain": domain, "status": "reachable",
                "latency_ms": elapsed, "status_code": response.status_code,
                "error_details": f"Resolved IP: {resolved_ip}\nHTTP Status: {response.status_code}{note}"}
    except httpx.TimeoutException:
        return {"name": name, "domain": domain, "status": "timeout",
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "error_details": f"TCP connection timed out after {TIMEOUT} seconds."}
    except (httpx.ConnectError, httpx.RemoteProtocolError) as exc:
        elapsed = round((time.monotonic() - start) * 1000, 1)
        message = str(exc).lower()
        status = "tls_failure" if "ssl" in message or "handshake" in message else "blocked"
        diag = "SSL/TLS Handshake failed. Common symptom of SNI-based deep packet blocking." \
            if status == "tls_failure" else "Connection actively reset or rejected."
        return {"name": name, "domain": domain, "status": status, "latency_ms": elapsed,
                "error_details": f"Socket Exception: {exc}\n{diag}"}
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "domain": domain, "status": "blocked",
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "error_details": f"Unclassified network error: {exc}"}


def test_social_media_accessibility() -> list[dict]:
    results = []
    for social in TARGET_SOCIAL_MEDIA:
        primary = test_website_reachability(social["name"], social["primary"])
        secondary = test_website_reachability(f"{social['name']} (API)", social["secondary"])
        primary_ok = primary["status"] == "reachable"
        secondary_ok = secondary["status"] == "reachable"
        status = "accessible" if primary_ok and secondary_ok \
            else "partial" if primary_ok or secondary_ok else "blocked"
        results.append({
            "name": social["name"], "primary": primary, "secondary": secondary, "status": status,
            "latency_ms": primary.get("latency_ms"),
            "error_details": primary.get("error_details") or secondary.get("error_details"),
        })
    return results


def scan_cdn_ips(ips: list[str], port: int = 443, max_concurrency: int = 300,
                 timeout: float = 0.5) -> dict:
    """Parallel TCP connect scan over a CDN IP list (upstream scanCdnIps)."""
    if not ips:
        return {"total_tested": 0, "reachable": 0, "average_latency_ms": 0, "ips": []}

    index = 0
    counter = {"reachable": 0, "latency_sum": 0, "latency_count": 0}

    def worker() -> None:
        nonlocal index
        while index < len(ips):
            ip = ips[index]
            index += 1
            start = time.monotonic()
            result = common.tcp_connect(ip, port, timeout)
            if result["reachable"]:
                counter["reachable"] += 1
                counter["latency_sum"] += result["latency_ms"] or 0
                counter["latency_count"] += 1

    workers = min(len(ips), max_concurrency)
    import threading
    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    avg = round(counter["latency_sum"] / counter["latency_count"]) if counter["latency_count"] else 0
    return {"total_tested": len(ips), "reachable": counter["reachable"],
            "average_latency_ms": avg, "ips": ips}


def _cdn_reachability() -> list[dict]:
    results = []
    for name, _domain, ips_loader in TARGET_CDNS:
        ips = ips_loader()
        sample = ips[:200]
        scan = scan_cdn_ips(sample)
        results.append({"name": name, **scan})
    return results


# --- Protocol accessibility -------------------------------------------------

def _test_protocol_http(domain: str, timeout: float = 4.0) -> dict:
    start = time.monotonic()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(f"http://{domain}", headers={"Connection": "close"})
        return {"protocol": "TCP HTTP", "domain": domain, "success": True,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "details": f"HTTP GET succeeded (Status: {response.status_code})"}
    except Exception as exc:  # noqa: BLE001
        return {"protocol": "TCP HTTP", "domain": domain, "success": False,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "details": f"Failed: {_brief(exc)}"}


def _test_protocol_https(domain: str, timeout: float = 4.0) -> dict:
    start = time.monotonic()
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(f"https://{domain}")
        return {"protocol": "TCP HTTPS", "domain": domain, "success": True,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "details": f"HTTPS GET succeeded (Status: {response.status_code})"}
    except Exception as exc:  # noqa: BLE001
        return {"protocol": "TCP HTTPS", "domain": domain, "success": False,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "details": f"Failed: {_brief(exc)}"}


def _test_protocol_udp(domain: str, timeout: float = 4.0) -> dict:
    """UDP via NTP (time.google.com/time.windows.com) or DNS query otherwise."""
    start = time.monotonic()
    try:
        ip = socket.gethostbyname(domain)
    except OSError as exc:
        return {"protocol": "UDP Connectivity", "domain": domain, "success": False,
                "latency_ms": None, "details": f"DNS resolution failed: {exc}"}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        if domain.startswith("time."):
            packet = b"\x1b" + b"\x00" * 47
            sock.sendto(packet, (ip, 123))
            data, _ = sock.recvfrom(1024)
            success = len(data) >= 4
            detail = f"NTP response received ({len(data)} bytes)"
        else:
            result = common.udp_dns_query(ip, "google.com", timeout)
            success = result["success"]
            detail = f"DNS response received: {', '.join(result['ips'][:3]) or 'no A records'}" if success \
                else f"DNS query failed: {result['error']}"
        return {"protocol": "UDP Connectivity", "domain": domain, "success": success,
                "latency_ms": round((time.monotonic() - start) * 1000, 1), "details": detail}
    except (socket.timeout, OSError) as exc:
        return {"protocol": "UDP Connectivity", "domain": domain, "success": False,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "details": f"UDP failed: {_brief(exc)}"}
    finally:
        sock.close()


def _test_protocol_doh(domain: str, timeout: float = 4.0) -> dict:
    start = time.monotonic()
    url = f"https://{domain}/resolve?name=google.com&type=A"
    if domain == "cloudflare-dns.com":
        url = f"https://{domain}/dns-query?name=google.com&type=A"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
        success = response.status_code == 200 and ("Address" in response.text or '"data"' in response.text)
        return {"protocol": "DNS-over-HTTPS", "domain": domain, "success": success,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "details": f"DoH query succeeded (Status: {response.status_code})" if success else f"DoH returned status {response.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {"protocol": "DNS-over-HTTPS", "domain": domain, "success": False,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "details": f"Failed: {_brief(exc)}"}


def _test_protocol_dot(domain: str, timeout: float = 4.0) -> dict:
    try:
        ip = socket.gethostbyname(domain)
    except OSError as exc:
        return {"protocol": "DNS-over-TLS", "domain": domain, "success": False,
                "latency_ms": None, "details": f"DNS resolution failed: {exc}"}
    start = time.monotonic()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        context = ssl.create_default_context()
        tls = context.wrap_socket(sock, server_hostname=domain)
        tls.connect((ip, 853))
        tls.close()
        return {"protocol": "DNS-over-TLS", "domain": domain, "success": True,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "details": "TLS connection to port 853 succeeded"}
    except (ssl.SSLError, OSError) as exc:
        return {"protocol": "DNS-over-TLS", "domain": domain, "success": False,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "details": f"Failed: {_brief(exc)}"}


def _test_protocol_icmp(domain: str, timeout: float = 4.0) -> dict:
    try:
        ip = socket.gethostbyname(domain)
    except OSError as exc:
        return {"protocol": "ICMP Ping", "domain": domain, "success": False,
                "latency_ms": None, "details": f"DNS resolution failed: {exc}"}
    start = time.monotonic()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except PermissionError:
        return {"protocol": "ICMP Ping", "domain": domain, "success": False,
                "latency_ms": None, "details": "ICMP requires elevated privileges"}
    except OSError as exc:
        return {"protocol": "ICMP Ping", "domain": domain, "success": False,
                "latency_ms": None, "details": f"ICMP unavailable: {exc}"}
    try:
        sock.settimeout(timeout)
        ident = random.randint(0, 0xFFFF)
        header = struct.pack(">BBHHH", 8, 0, 0, ident, 1)
        sock.sendto(header + b"\x00" * 12, (ip, 1))
        data, _ = sock.recvfrom(1024)
        success = len(data) >= 4 and data[20:22] == struct.pack(">H", ident)
        return {"protocol": "ICMP Ping", "domain": domain, "success": success,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "details": "ICMP echo reply received" if success else "No matching ICMP echo reply"}
    except (socket.timeout, OSError) as exc:
        return {"protocol": "ICMP Ping", "domain": domain, "success": False,
                "latency_ms": round((time.monotonic() - start) * 1000, 1),
                "details": f"Ping failed: {_brief(exc)}"}
    finally:
        sock.close()


_PROTOCOL_TESTERS = {
    "TCP HTTP": _test_protocol_http,
    "TCP HTTPS": _test_protocol_https,
    "UDP Connectivity": _test_protocol_udp,
    "DNS-over-HTTPS": _test_protocol_doh,
    "DNS-over-TLS": _test_protocol_dot,
    "ICMP Ping": _test_protocol_icmp,
}


def protocol_accessibility() -> dict:
    summaries = []
    for name, (domains, description) in PROTOCOL_DOMAINS.items():
        tester = _PROTOCOL_TESTERS[name]
        results = [tester(d) for d in domains]
        summaries.append({
            "protocol_name": name,
            "description": description,
            "is_supported": any(r["success"] for r in results),
            "is_blocked": False,
            "results": results,
        })
    has_support = any(s["is_supported"] for s in summaries)
    for summary in summaries:
        summary["is_blocked"] = not summary["is_supported"] and has_support
    return {
        "name": "Protocol Accessibility",
        "success": has_support,
        "supported": sum(1 for s in summaries if s["is_supported"]),
        "blocked": sum(1 for s in summaries if s["is_blocked"]),
        "summaries": summaries,
    }


def _brief(exc: BaseException) -> str:
    message = str(exc)
    return message[:150] + ("..." if len(message) > 150 else "")


def run_all() -> dict:
    """Run the full diagnostic battery. Returns a structured report."""
    dns = check_dns_resolution()
    ipv4 = check_ipv4_connectivity()
    ipv6 = check_ipv6_connectivity()
    https = check_https_traffic()
    dns_analysis = analyze_dns_providers()
    domestic = fetch_public_ip(domestic=True)
    international = fetch_public_ip(domestic=False)
    routing = analyze_public_ips(domestic, international)
    tls_analysis = analyze_tls_targets(international.get("message", "").replace("IP retrieved: ", "") or None)
    websites = [test_website_reachability(w["name"], w["domain"]) for w in TARGET_WEBSITES]
    social = test_social_media_accessibility()
    cdn = _cdn_reachability()
    protocols = protocol_accessibility()

    overall = any([
        dns["success"], ipv4["success"], ipv6["success"], https["success"],
        dns_analysis["success"], tls_analysis["success"],
        domestic["success"], international["success"],
        any(w["status"] == "reachable" for w in websites),
        any(c["reachable"] > 0 for c in cdn),
        any(s["status"] in ("accessible", "partial") for s in social),
        protocols["success"],
    ])

    return {
        "name": "Internet Diagnostics",
        "overall_internet_access": overall,
        "checks": {
            "dns_resolution": dns,
            "ipv4_connectivity": ipv4,
            "ipv6_connectivity": ipv6,
            "https_traffic": https,
            "dns_provider_analysis": dns_analysis,
            "domestic_ip": domestic,
            "international_ip": international,
            "ip_routing_gateway_analysis": routing,
            "tls_interception_analysis": tls_analysis,
            "website_reachability": {"success": any(w["status"] == "reachable" for w in websites),
                                     "results": websites},
            "social_media_accessibility": {"success": any(s["status"] in ("accessible", "partial") for s in social),
                                           "results": social},
            "cdn_reachability": {"success": any(c["reachable"] > 0 for c in cdn), "results": cdn},
            "protocol_accessibility": protocols,
        },
    }