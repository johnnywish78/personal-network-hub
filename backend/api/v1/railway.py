"""Railway API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...providers.railway.client import RailwayError
from ...services.state import AppState
from .deps import get_state

router = APIRouter(prefix="/railway", tags=["railway"])


class TokenRequest(BaseModel):
    token: str


@router.get("/status")
def status(state: AppState = Depends(get_state)):
    rw = state.railway.check()
    return {"configured": state.vault.has("railway_token"), **rw}


@router.post("/auth")
def auth(body: TokenRequest, state: AppState = Depends(get_state)):
    token = body.token.strip()
    if not token:
        raise HTTPException(400, "token is required")
    state.vault.set("railway_token", token)
    state.logs.success("railway", "API token saved (masked in vault)")
    return {"ok": True}


@router.delete("/auth")
def deauth(state: AppState = Depends(get_state)):
    state.vault.delete("railway_token")
    state.logs.info("railway", "API token removed")
    return {"ok": True}


@router.get("/projects")
def projects(state: AppState = Depends(get_state)):
    try:
        return {"projects": state.railway.projects()}
    except RailwayError as exc:
        raise HTTPException(502, str(exc))


@router.get("/projects/{project_id}/services")
def services(project_id: str, state: AppState = Depends(get_state)):
    try:
        return {"services": state.railway.services(project_id)}
    except RailwayError as exc:
        raise HTTPException(502, str(exc))


@router.get("/projects/{project_id}/deployments")
def deployments(project_id: str, service_id: str | None = None, state: AppState = Depends(get_state)):
    try:
        return {"deployments": state.railway.deployments(project_id, service_id)}
    except RailwayError as exc:
        raise HTTPException(502, str(exc))


@router.get("/projects/{project_id}/domains")
def domains(project_id: str, state: AppState = Depends(get_state)):
    try:
        return {"domains": state.railway.domains(project_id)}
    except RailwayError as exc:
        raise HTTPException(502, str(exc))


@router.get("/projects/{project_id}/services/{service_id}/variables")
def variables_metadata(project_id: str, service_id: str, state: AppState = Depends(get_state)):
    """Returns variable NAMES only; secret values are never exposed."""
    try:
        return {"variables": state.railway.variables_metadata(project_id, service_id)}
    except RailwayError as exc:
        raise HTTPException(502, str(exc))


@router.get("/dashboard-url")
def dashboard_url():
    return {"url": "https://railway.com/dashboard", "action": "open"}
