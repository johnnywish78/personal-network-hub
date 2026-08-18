"""System routes: version, settings, logs, uptime."""

from __future__ import annotations

import time as _time

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...services.state import AppState
from ...version import get_version
from .deps import get_state

router = APIRouter(tags=["system"])

VERSION = get_version()

_START_TIME = _time.monotonic()


class SettingRequest(BaseModel):
    key: str
    value: object


@router.get("/version")
def version():
    return {"version": VERSION, "name": "Johnny Personal Network Hub", "codename": "JPNH"}


@router.get("/uptime")
def uptime():
    """Seconds since the backend (and therefore the app) started."""
    return {"uptime_seconds": int(_time.monotonic() - _START_TIME)}


@router.get("/settings")
def settings(state: AppState = Depends(get_state)):
    return {"settings": state.settings.all()}


@router.post("/settings")
def set_setting(body: SettingRequest, state: AppState = Depends(get_state)):
    state.settings.set(body.key, body.value)
    return {"ok": True}


@router.get("/logs")
def logs(level: str | None = None, state: AppState = Depends(get_state)):
    return {"logs": state.logs.entries(level)}


@router.delete("/logs")
def clear_logs(state: AppState = Depends(get_state)):
    state.logs.clear()
    return {"ok": True}


@router.get("/logs/export")
def export_logs(state: AppState = Depends(get_state)):
    return {"content": state.logs.export()}


@router.get("/history")
def history(state: AppState = Depends(get_state)):
    return {"history": state.history.list()}
