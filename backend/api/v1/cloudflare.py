"""Cloudflare API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...providers.cloudflare.client import CloudflareError
from ...services.state import AppState
from .deps import get_state

router = APIRouter(prefix="/cloudflare", tags=["cloudflare"])


class TokenRequest(BaseModel):
    token: str


@router.get("/status")
def status(state: AppState = Depends(get_state)):
    cf = state.cloudflare.check()
    return {"configured": state.vault.has("cloudflare_token"), **cf}


@router.post("/auth")
def auth(body: TokenRequest, state: AppState = Depends(get_state)):
    token = body.token.strip()
    if not token:
        raise HTTPException(400, "token is required")
    state.vault.set("cloudflare_token", token)
    state.logs.success("cloudflare", "API token saved (masked in vault)")
    return {"ok": True}


@router.delete("/auth")
def deauth(state: AppState = Depends(get_state)):
    state.vault.delete("cloudflare_token")
    state.logs.info("cloudflare", "API token removed")
    return {"ok": True}


@router.get("/accounts")
def accounts(state: AppState = Depends(get_state)):
    try:
        return {"accounts": state.cloudflare.accounts()}
    except CloudflareError as exc:
        raise HTTPException(502, str(exc))


@router.get("/zones")
def zones(state: AppState = Depends(get_state)):
    try:
        return {"zones": state.cloudflare.zones()}
    except CloudflareError as exc:
        raise HTTPException(502, str(exc))


@router.get("/workers/{account_id}")
def workers(account_id: str, state: AppState = Depends(get_state)):
    try:
        return {"workers": state.cloudflare.workers(account_id)}
    except CloudflareError as exc:
        raise HTTPException(502, str(exc))


@router.get("/workers/{account_id}/{name}")
def worker_detail(account_id: str, name: str, state: AppState = Depends(get_state)):
    try:
        script = state.cloudflare.worker_script(account_id, name)
        versions = state.cloudflare.worker_versions(account_id, name)
        return {"script": script, "versions": versions}
    except CloudflareError as exc:
        raise HTTPException(502, str(exc))


@router.get("/pages/{account_id}")
def pages_projects(account_id: str, state: AppState = Depends(get_state)):
    try:
        return {"projects": state.cloudflare.pages_projects(account_id)}
    except CloudflareError as exc:
        raise HTTPException(502, str(exc))


@router.get("/pages/{account_id}/{project}/deployments")
def pages_deployments(account_id: str, project: str, state: AppState = Depends(get_state)):
    try:
        return {"deployments": state.cloudflare.pages_deployments(account_id, project)}
    except CloudflareError as exc:
        raise HTTPException(502, str(exc))


@router.get("/dashboard-url")
def dashboard_url():
    return {"url": "https://dash.cloudflare.com", "action": "open"}
