"""First-run setup (skippable wizard) API."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...services.state import AppState
from .deps import get_state

router = APIRouter(prefix="/setup", tags=["setup"])


class SetupComplete(BaseModel):
    skipped: bool = False


@router.get("/status")
def setup_status(state: AppState = Depends(get_state)):
    """Whether first-run wizard still needs attention."""
    completed = bool(state.settings.get("setup.completed"))
    return {"completed": completed,
            "wizard_required": not completed and not bool(state.settings.get("setup.skipped"))}


@router.post("/complete")
def setup_complete(body: SetupComplete, state: AppState = Depends(get_state)):
    state.settings.set("setup.completed", True)
    state.settings.set("setup.skipped", bool(body.skipped))
    state.logs.info("setup", "first-run wizard completed" + (" (skipped)" if body.skipped else ""))
    return {"ok": True}


@router.get("/info")
def setup_info(state: AppState = Depends(get_state)):
    """Summary of what is configured, used by the wizard screens."""
    return {
        "configured": {
            "github": state.vault.has("github_token"),
            "cloudflare": state.vault.has("cloudflare_token"),
            "railway": state.vault.has("railway_token"),
            "xray": state.xray.status()["installed"],
        },
        "services": len(state.service_list()),
        "configs": state.config_store.counts(),
    }