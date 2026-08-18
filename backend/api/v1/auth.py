"""Authentication / credential management for external services.

Secrets are stored in the local vault. This API exposes masked presence
only; actual secret values never leave the backend.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...services.state import AppState
from .deps import get_state

router = APIRouter(prefix="/auth", tags=["auth"])


class SecretRequest(BaseModel):
    key: str
    value: str


@router.get("/status")
def auth_status(state: AppState = Depends(get_state)):
    """Which external services have credentials configured (masked only)."""
    keys = state.vault.keys()
    return {
        "configured": {
            "cloudflare": state.vault.has("cloudflare_token"),
            "railway": state.vault.has("railway_token"),
            "github": state.vault.has("github_token"),
        },
        "other_keys": [k for k in keys if k not in ("cloudflare_token", "railway_token", "github_token")],
    }


@router.get("/secrets")
def list_secrets(state: AppState = Depends(get_state)):
    """Masked preview of stored secret keys. Values never exposed."""
    return {"secrets": state.vault.masked()}


@router.post("/secrets")
def set_secret(body: SecretRequest, state: AppState = Depends(get_state)):
    key = body.key.strip()
    if not key or not body.value.strip():
        raise HTTPException(400, "key and value are required")
    state.vault.set(key, body.value)
    state.logs.success("auth", f"secret '{key}' stored (masked)")
    return {"ok": True}


@router.delete("/secrets/{key}")
def delete_secret(key: str, state: AppState = Depends(get_state)):
    state.vault.delete(key)
    state.logs.info("auth", f"secret '{key}' removed")
    return {"ok": True}
