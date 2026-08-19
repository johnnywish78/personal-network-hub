"""Client detection and hand-off routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...services.state import AppState
from .deps import get_state

router = APIRouter(prefix="/clients", tags=["clients"])


class PathRequest(BaseModel):
    path: str


@router.get("")
def clients(state: AppState = Depends(get_state)):
    return {"clients": state.client_status()}


@router.post("/{client_id}/path")
def set_client_path(client_id: str, body: PathRequest, state: AppState = Depends(get_state)):
    valid = {"v2rayN", "hiddify", "v2box"}
    if client_id not in valid:
        raise HTTPException(400, f"unknown client: {client_id}")
    state.settings.set(f"client_paths.{client_id}", body.path.strip())
    state.logs.info("clients", f"set path for {client_id}")
    return {"ok": True}


@router.get("/handoff/format")
def handoff_formats(config_id: str, fmt: str, state: AppState = Depends(get_state)):
    """Provide hand-off payload (URI/JSON) for external clients."""
    cfg = state.config_store.get(config_id)
    if not cfg:
        raise HTTPException(404, "config not found")
    from ...configs import exporter as config_exporter
    if fmt == "uri":
        content = config_exporter.export_uris([cfg])
        return {"ok": True, "content": content, "format": "uri"}
    if fmt == "json":
        return {"ok": True, "content": config_exporter.export_json([cfg]), "format": "json"}
    raise HTTPException(400, f"unsupported hand-off format: {fmt}")
