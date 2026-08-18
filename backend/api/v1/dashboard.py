"""Dashboard, auth status, and top-level status endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from ...configs.storage import ConfigStore
from ...network import diagnostics as netdiag
from ...services.client_detector import detect_clients
from ...services.state import AppState
from .deps import get_state

router = APIRouter(tags=["dashboard"])


@router.get("/ping")
def ping():
    return {"pong": True, "time": time.time()}


@router.get("/dashboard")
def dashboard(state: AppState = Depends(get_state)):
    """Compact, useful dashboard data."""
    config_counts = state.config_store.counts()

    # Internet status
    internet = netdiag.internet_check()
    public_ip = netdiag.public_ip() if internet.get("status") == "online" else {"status": "offline"}

    # External service status (with graceful degradation)
    cf = state.cloudflare.check()
    rw = state.railway.check()
    gh = state.github.check()

    # Providers
    providers = state.provider_status()

    # Xray
    xray = state.xray.status()

    # Clients
    clients = state.client_status()

    return {
        "internet": {
            "status": internet.get("status"),
            "public_ip": public_ip.get("ip"),
            "latency_ms": internet.get("latency_ms"),
        },
        "services": {
            "cloudflare": cf,
            "railway": rw,
            "github": gh,
        },
        "providers": providers,
        "configs": config_counts,
        "xray": xray,
        "clients": clients,
        "generated_at": internet.get("timestamp"),
    }
