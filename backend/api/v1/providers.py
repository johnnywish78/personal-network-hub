"""Provider hub routes: list providers, open, configure, provider actions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...services.state import AppState
from .deps import get_state

router = APIRouter(prefix="/providers", tags=["providers"])


class PanelUrlRequest(BaseModel):
    panel_url: str


class ImportRequest(BaseModel):
    payload: str


@router.get("")
def list_providers(state: AppState = Depends(get_state)):
    return {"providers": state.providers.describe_all()}


@router.get("/status")
def provider_status(state: AppState = Depends(get_state)):
    return {"providers": state.provider_status()}


@router.get("/{name}")
def get_provider(name: str, state: AppState = Depends(get_state)):
    adapter = state.providers.get(name)
    if not adapter:
        raise HTTPException(404, f"unknown provider: {name}")
    return adapter.describe()


@router.post("/{name}/open")
def open_provider(name: str, state: AppState = Depends(get_state)):
    adapter = state.providers.get(name)
    if not adapter:
        raise HTTPException(404, f"unknown provider: {name}")
    return adapter.open()


@router.post("/{name}/configure")
def configure_provider(name: str, body: PanelUrlRequest, state: AppState = Depends(get_state)):
    adapter = state.providers.get(name)
    if not adapter:
        raise HTTPException(404, f"unknown provider: {name}")
    if not hasattr(adapter, "set_panel_url"):
        raise HTTPException(400, f"{name} does not support configuration")
    result = adapter.set_panel_url(body.panel_url.strip())
    state.settings.set(f"provider_urls.{name}", body.panel_url.strip())
    state.logs.info("providers", f"configured {name} panel URL")
    return result


@router.post("/{name}/import")
def import_provider(name: str, body: ImportRequest, state: AppState = Depends(get_state)):
    adapter = state.providers.get(name)
    if not adapter:
        raise HTTPException(404, f"unknown provider: {name}")
    parsed = adapter.import_config(body.payload)
    return {"ok": True, "parsed_count": len(parsed), "parsed": parsed}


@router.post("/{name}/parse")
def parse_provider(name: str, body: ImportRequest, state: AppState = Depends(get_state)):
    adapter = state.providers.get(name)
    if not adapter:
        raise HTTPException(404, f"unknown provider: {name}")
    return adapter.parse_config(body.payload)


@router.post("/{name}/action/{action}")
def provider_action(name: str, action: str, state: AppState = Depends(get_state)):
    """Generic action dispatch. Only supported actions are executed."""
    adapter = state.providers.get(name)
    if not adapter:
        raise HTTPException(404, f"unknown provider: {name}")
    if not adapter.supports_action(action):
        raise HTTPException(400, f"{name} does not support action '{action}'")
    handler = getattr(adapter, action, None)
    if not callable(handler):
        raise HTTPException(400, f"{name} has no handler for '{action}'")
    return handler()
