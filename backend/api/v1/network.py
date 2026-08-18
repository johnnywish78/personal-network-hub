"""Network Lab API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...network import diagnostics as netdiag
from ...network import dns as dns_mod
from ...network import latency as latency_mod
from ...network import tcp as tcp_mod
from ...services.state import AppState
from .deps import get_state

router = APIRouter(prefix="/network", tags=["network"])


class HostRequest(BaseModel):
    host: str
    port: int | None = None


class CleanIpRequest(BaseModel):
    address: str
    ports: list[int] | None = None


class DnsRequest(BaseModel):
    host: str
    resolver: str = "system"


@router.get("/lab")
def full_lab(state: AppState = Depends(get_state)):
    state.logs.info("network", "running network lab diagnostics")
    return netdiag.run_network_lab()


@router.get("/internet")
def internet(state: AppState = Depends(get_state)):
    return netdiag.internet_check()


@router.get("/public-ip")
def public_ip(state: AppState = Depends(get_state)):
    return netdiag.public_ip()


@router.get("/dns")
def dns_matrix(state: AppState = Depends(get_state)):
    return {"results": dns_mod.dns_latency_multi()}


@router.post("/dns/query")
def dns_query(body: DnsRequest, state: AppState = Depends(get_state)):
    return dns_mod.query_host(body.host.strip(), body.resolver)


@router.post("/domain")
def domain(body: HostRequest, state: AppState = Depends(get_state)):
    return netdiag.domain_check(body.host.strip(), body.port)


@router.post("/tcp")
def tcp(body: HostRequest, state: AppState = Depends(get_state)):
    return tcp_mod.tcp_check(body.host.strip(), body.port or 443)


@router.post("/tls")
def tls(body: HostRequest, state: AppState = Depends(get_state)):
    return tcp_mod.tls_check(body.host.strip(), body.port or 443, sni=body.host.strip())


@router.get("/latency")
def latency(state: AppState = Depends(get_state)):
    return {"results": netdiag.latency_matrix()}


@router.post("/clean-ip")
def clean_ip(body: CleanIpRequest, state: AppState = Depends(get_state)):
    return {"results": netdiag.clean_ip_test(body.address.strip(), body.ports)}
