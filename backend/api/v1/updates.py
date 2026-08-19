"""Update Manager API routes + Project Registry routes.

Conventions follow the rest of the backend: Pydantic bodies, ``Depends``
for state, ``{"ok": True}`` for mutations, HTTPException for client errors.
Nothing here returns or accepts credentials.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...updates.manager import UpdateManagerError
from ...services.state import AppState
from .deps import get_state

projects_router = APIRouter(prefix="/projects", tags=["projects"])
updates_router = APIRouter(prefix="/updates", tags=["updates"])


class CheckRequest(BaseModel):
    project_id: Optional[str] = None


class UpdateRequest(BaseModel):
    project_id: str
    confirm: bool = False


class UpdateAllRequest(BaseModel):
    confirm: bool = False
    dry_run: bool = False


# --- Project Registry -----------------------------------------------------

@projects_router.get("")
def list_projects(state: AppState = Depends(get_state)):
    return {"projects": state.updates.status_all()["projects"]}


@projects_router.get("/{project_id}")
def get_project(project_id: str, state: AppState = Depends(get_state)):
    project = state.updates.registry.get(project_id)
    if not project:
        raise HTTPException(404, f"unknown project '{project_id}'")
    entry = state.updates.status_entry(project)
    return {"project": entry}


# --- Update Manager -------------------------------------------------------

@updates_router.get("")
def updates_overview(state: AppState = Depends(get_state)):
    """Combined status without hitting the network (uses cached state)."""
    return state.updates.status_all(check=False)


@updates_router.post("/check")
def check_updates(body: CheckRequest, state: AppState = Depends(get_state)):
    """Query upstream for one project or all; never modifies anything."""
    try:
        if body.project_id:
            plan = state.updates.check(body.project_id)
            return {"project_id": body.project_id, "plan": plan}
        return state.updates.dry_run()
    except UpdateManagerError as exc:
        raise HTTPException(400, str(exc)) from exc


@updates_router.post("/dry-run")
def dry_run(body: CheckRequest, state: AppState = Depends(get_state)):
    """Check-only plan; guarantees no files are modified."""
    try:
        if body.project_id:
            return {"project_id": body.project_id, "plan": state.updates.check(body.project_id)}
        return state.updates.dry_run()
    except UpdateManagerError as exc:
        raise HTTPException(400, str(exc)) from exc


@updates_router.post("/{project_id}/update")
def update_project(project_id: str, body: UpdateRequest, state: AppState = Depends(get_state)):
    """Update one project. confirm=true acknowledges overwriting local changes."""
    if body.project_id != project_id:
        raise HTTPException(400, "project_id mismatch")
    try:
        return state.updates.update(project_id, confirm=body.confirm)
    except UpdateManagerError as exc:
        raise HTTPException(400, str(exc)) from exc


@updates_router.post("/{project_id}/dry-run")
def update_project_dry_run(project_id: str, state: AppState = Depends(get_state)):
    try:
        return state.updates.dry_run(project_id)
    except UpdateManagerError as exc:
        raise HTTPException(400, str(exc)) from exc


@updates_router.post("/all")
def update_all(body: UpdateAllRequest, state: AppState = Depends(get_state)):
    try:
        return state.updates.update_all(confirm=body.confirm, dry_run=body.dry_run)
    except UpdateManagerError as exc:
        raise HTTPException(400, str(exc)) from exc


@updates_router.get("/history")
def update_history(state: AppState = Depends(get_state)):
    return {"history": state.update_history.list()}


@updates_router.get("/backups")
def list_backups(project: Optional[str] = None, state: AppState = Depends(get_state)):
    return {"backups": state.updates.backup.list(project=project)}


@updates_router.post("/rollback/{backup_id}")
def rollback(backup_id: str, state: AppState = Depends(get_state)):
    try:
        return state.updates.rollback(backup_id)
    except (UpdateManagerError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc