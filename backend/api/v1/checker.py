"""Network Checker API routes (native integration).

Attribution: the underlying tool algorithms are a port of the GPL-3.0
mirarr-app/network-checker project. See backend/network/checker.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...network.checker import configs as config_tools
from ...network.checker import diagnostics as diag
from ...network.checker import probes
from ...network.checker import scanners
from ...network.checker import xray_scan
from ...network.checker import chain as chain_tools
from ...network.checker import cloudflare_fix
from ...network.checker import sni_spoof_check
from ...network.checker.data import (akamai_ip_ranges, dns_providers, dns_ranges,
                                     edge_ip_ranges, netlify_predefined, top_domains)
from ...services.state import AppState
from .deps import get_state

router = APIRouter(prefix="/checker", tags=["network-checker"])


class DomainCheckRequest(BaseModel):
    targets: list[str] | None = None
    timeout: float = 3.0
    concurrency: int = 10


class DnsLatencyRequest(BaseModel):
    providers: list[dict] | None = None
    timeout: float = 2.0
    concurrency: int = 10


class DnsHunterRequest(BaseModel):
    ranges: list[str] | None = None
    target: str = "twitter"
    custom_domain: str = ""
    concurrency: int = 50
    timeout: float = 2.0
    check_secure_dns: bool = False
    max_ips: int = 500


class EdgeIpRequest(BaseModel):
    ip_input: str
    test_domain: str = "chatgpt.com"
    test_path: str = "/"
    port: int = 443
    timeout: float = 3.0
    max_workers: int = 20
    test_download: bool = True
    download_size: int = 100 * 1024


class AkamaiRequest(BaseModel):
    ip_input: str | None = None
    port: int = 443
    timeout: float = 2.0
    max_workers: int = 100


class VlessModifyRequest(BaseModel):
    configs: str
    ips: str
    parse_ips: bool = True


class NetlifyGenerateRequest(BaseModel):
    uuid: str
    path: str
    netlify_domain: str
    xhttp_object: str
    snis: list[str]
    ips: list[str]


class XrayScanRequest(BaseModel):
    ip_input: str
    config_json: str
    concurrency: int = 5
    timeout: float = 10.0
    startup_delay: float = 2.0
    test_url: str = xray_scan.DEFAULT_TEST_URL
    max_ips: int = 200


class SniSpoofRequest(BaseModel):
    targets: str | None = None
    ports: list[int] | None = None
    timeout: float = 5.0
    retries: int = 3
    concurrency: int = 20
    enable_ip_check: bool = True
    manual_ip: str = ""


class CloudflareFixRequest(BaseModel):
    links: str
    socks_port: int = 10808
    http_port: int = 10809
    dns_server: str = cloudflare_fix.DEFAULT_DNS_SERVER
    remark_suffix: str = "-custom"
    fingerprint: str = "unsafe"
    alpn: str = "http/1.1"
    cipher_suites: str = cloudflare_fix.DEFAULT_CIPHER_SUITES
    enable_finalmask: bool = True


class ChainRequest(BaseModel):
    links: str
    socks_port: int = 10808
    http_port: int = 10809


@router.get("/metadata")
def metadata(state: AppState = Depends(get_state)):
    return {
        "top_domains": top_domains(),
        "dns_providers": dns_providers(),
        "dns_ranges": dns_ranges(),
        "akamai_ranges": akamai_ip_ranges(),
        "edge_ranges": edge_ip_ranges(),
        "netlify_predefined": netlify_predefined(),
        "defaults": {
            "domain_check": {"timeout": 3.0, "concurrency": 10},
            "dns_latency": {"timeout": 2.0, "concurrency": 10},
            "dns_hunter": {"targets": ["twitter", "youtube", "custom"], "timeout": 2.0,
                           "concurrency": 50, "max_ips": 500},
            "edge_ip": {"test_domain": "chatgpt.com", "port": 443, "timeout": 3.0,
                        "max_workers": 20},
            "akamai": {"port": 443, "timeout": 2.0, "max_workers": 100},
            "xray_scan": {"concurrency": 5, "timeout": 10.0, "startup_delay": 2.0,
                          "test_url": xray_scan.DEFAULT_TEST_URL},
            "sni_spoof_check": {
                "targets": [
                    t.strip()
                    for t in sni_spoof_check.DEFAULT_TARGETS.splitlines()
                    if t.strip()
                ],
                "ports": sni_spoof_check.DEFAULT_PORTS,
                "timeout": 5.0,
                "retries": 3,
                "concurrency": 20,
            },
            "cloudflare_fix": {"dns_server": cloudflare_fix.DEFAULT_DNS_SERVER,
                               "fingerprint": "unsafe", "alpn": "http/1.1",
                               "remark_suffix": "-custom"},
            "chain": {"socks_port": 10808, "http_port": 10809},
        },
    }


@router.get("/internet-diagnostics")
def internet_diagnostics(state: AppState = Depends(get_state)):
    state.logs.info("network", "running network checker internet diagnostics")
    return diag.run_all()


@router.get("/protocols")
def protocols(state: AppState = Depends(get_state)):
    return diag.protocol_accessibility()


@router.post("/domain-check")
def domain_check(body: DomainCheckRequest, state: AppState = Depends(get_state)):
    targets = body.targets or probes.default_domains()
    return {"total": len(targets), "results": probes.check_domains(targets, body.timeout,
                                                                   body.concurrency)}


@router.post("/dns-latency")
def dns_latency(body: DnsLatencyRequest, state: AppState = Depends(get_state)):
    providers = body.providers if body.providers else probes.default_providers()
    return {"total": len(providers), "results": probes.dns_latency_multi(providers, body.timeout,
                                                                         body.concurrency)}


@router.post("/dns-hunter")
def dns_hunter(body: DnsHunterRequest, state: AppState = Depends(get_state)):
    ranges = body.ranges if body.ranges else [c for p in dns_ranges() for c in p["ranges"]]
    result = scanners.dns_hunter_scan(ranges, body.target, body.custom_domain,
                                      body.concurrency, body.timeout,
                                      body.check_secure_dns, body.max_ips)
    return result


@router.post("/edge-ip")
def edge_ip(body: EdgeIpRequest, state: AppState = Depends(get_state)):
    config = scanners.EdgeScanConfig(
        test_domain=body.test_domain, test_path=body.test_path, port=body.port,
        timeout=body.timeout, max_workers=body.max_workers,
        test_download=body.test_download, download_size=body.download_size)
    return scanners.edge_ip_scan(body.ip_input, config)


@router.post("/akamai")
def akamai(body: AkamaiRequest, state: AppState = Depends(get_state)):
    ip_input = body.ip_input if body.ip_input else "\n".join(akamai_ip_ranges())
    config = scanners.AkamaiScanConfig(port=body.port, timeout=body.timeout,
                                       max_workers=body.max_workers)
    return scanners.akamai_scan(ip_input, config)


@router.post("/vless-modify")
def vless_modify(body: VlessModifyRequest, state: AppState = Depends(get_state)):
    return config_tools.modify_vless_configs(body.configs, body.ips, body.parse_ips)


@router.post("/netlify-generate")
def netlify_generate(body: NetlifyGenerateRequest, state: AppState = Depends(get_state)):
    if not (body.uuid.strip() and body.path.strip() and body.netlify_domain.strip()
            and body.xhttp_object.strip() and body.snis and body.ips):
        raise HTTPException(status_code=400, detail="Please fill all fields")
    return config_tools.generate_netlify_configs(
        body.uuid.strip(), body.path.strip(), body.netlify_domain.strip(),
        body.xhttp_object.strip(), [s.strip() for s in body.snis],
        [i.strip() for i in body.ips])


@router.post("/xray-scan")
def xray_scan_endpoint(body: XrayScanRequest, state: AppState = Depends(get_state)):
    try:
        return xray_scan.cdn_scan(body.ip_input, body.config_json, body.concurrency,
                                  body.timeout, body.startup_delay, body.test_url,
                                  body.max_ips)
    except xray_scan.XrayUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sni-spoof-check")
def sni_spoof_check_endpoint(body: SniSpoofRequest, state: AppState = Depends(get_state)):
    state.logs.info("network", "running network checker SNI spoof check")
    try:
        return sni_spoof_check.sni_spoof_check(
            body.targets, body.ports, body.timeout, body.retries,
            body.concurrency, body.enable_ip_check, body.manual_ip)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sni-spoof-check/report")
def sni_spoof_check_report(body: dict, state: AppState = Depends(get_state)):
    data = body.get("data") or {}
    return {"report": sni_spoof_check.generate_report(data)}


@router.post("/cloudflare-fix")
def cloudflare_fix_endpoint(body: CloudflareFixRequest, state: AppState = Depends(get_state)):
    state.logs.info("network", "running network checker Cloudflare Fix")
    options = {
        "socks_port": body.socks_port, "http_port": body.http_port,
        "dns_server": body.dns_server, "remark_suffix": body.remark_suffix,
        "fingerprint": body.fingerprint,
        "alpn": [a.strip() for a in body.alpn.split(",") if a.strip()],
        "cipher_suites": body.cipher_suites, "enable_finalmask": body.enable_finalmask,
    }
    result = cloudflare_fix.transform_vless_lines(body.links, **options)
    if not result["total"] and not result["errors"]:
        raise HTTPException(status_code=400, detail="Please paste one or more VLESS links")
    return result


@router.post("/chain")
def chain_generate(body: ChainRequest, state: AppState = Depends(get_state)):
    state.logs.info("network", "running network checker chain generator")
    result = chain_tools.generate_chain(body.links, body.socks_port, body.http_port)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result