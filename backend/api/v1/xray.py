"""Xray API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...services.state import AppState
from .deps import get_state

router = APIRouter(prefix="/xray", tags=["xray"])


class ConfigPathRequest(BaseModel):
    config_path: str


@router.get("/status")
def status(state: AppState = Depends(get_state)):
    return state.xray.status()


@router.post("/start")
def start(body: ConfigPathRequest | None = None, state: AppState = Depends(get_state)):
    result = state.xray.start(body.config_path if body else None)
    state.logs.info("xray", f"start requested: {result}")
    return result


@router.post("/stop")
def stop(state: AppState = Depends(get_state)):
    result = state.xray.stop()
    state.logs.info("xray", f"stop requested: {result}")
    return result


@router.post("/restart")
def restart(body: ConfigPathRequest | None = None, state: AppState = Depends(get_state)):
    result = state.xray.restart(body.config_path if body else None)
    state.logs.info("xray", f"restart requested: {result}")
    return result


@router.post("/validate")
def validate(body: ConfigPathRequest, state: AppState = Depends(get_state)):
    return state.xray.validate_config(body.config_path)


@router.post("/set-config")
def set_config(body: ConfigPathRequest, state: AppState = Depends(get_state)):
    state.settings.set("xray.config_path", body.config_path)
    return {"ok": True}
