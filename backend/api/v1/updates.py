"""Update Manager API routes + Project Registry routes.

Conventions follow the rest of the backend: Pydantic bodies, ``Depends``
for state, ``{"ok": True}`` for mutations, HTTPException for client errors.
Nothing here returns or accepts credentials.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...updates.manager import UpdateManagerError
from ...updates.self_update import (_validate_staged, clear_pending_apply,
                                    find_appimage_asset, pending_apply_info,
                                    request_appimage_apply, request_apply,
                                    resolve_appimage_target, runtime_mode,
                                    sha256_file, stage_appimage)
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


class StageAppImageRequest(BaseModel):
    artifact_path: Optional[str] = None
    artifact_url: Optional[str] = None


def _live_appimage_download(project, source) -> tuple[str, Any, Any]:
    """Discover the latest release's AppImage asset and download it into the
    update cache. Returns ``(artifact_path, version, release_tag)``; raises
    HTTPException with a human-readable reason when nothing can be staged.
    """
    try:
        available = source.check_available(project)
    except UpdateManagerError as exc:
        raise HTTPException(400, str(exc)) from exc
    asset = find_appimage_asset(available)
    if not asset:
        raise HTTPException(400, (
            "no AppImage asset found on the latest release. The release may "
            "be reachable but publish only source archives."))
    try:
        from ...storage.paths import update_cache_dir
        cache = update_cache_dir()
        cache.mkdir(parents=True, exist_ok=True)
        downloaded = source.download_asset(project, asset, cache)
    except UpdateManagerError as exc:
        raise HTTPException(400, str(exc)) from exc
    return (str(downloaded), (available or {}).get("version"),
            (available or {}).get("release_tag"))


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
    data = state.updates.status_all(check=False)
    data["runtime"] = runtime_mode()
    data["pending_apply"] = pending_apply_info()
    target = resolve_appimage_target()
    data["appimage_target"] = target
    data["appimage_sha256"] = sha256_file(target) if target else None
    return data


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


@updates_router.get("/runtime")
def runtime(state: AppState = Depends(get_state)):
    """How JPNH is running (source/appimage/deb) + pending self-update info."""
    target = resolve_appimage_target()
    return {
        "mode": runtime_mode(),
        "appimage": __import__("backend.updates.self_update", fromlist=["appimage_target"]).appimage_target(),
        "appimage_target": target,
        "appimage_sha256": sha256_file(target) if target else None,
        "pending_apply": pending_apply_info(),
    }


@updates_router.post("/{project_id}/stage-appimage")
def stage_appimage_update(project_id: str, body: StageAppImageRequest,
                          state: AppState = Depends(get_state)):
    """Download (or take from a local fixture) the AppImage release artifact for
    a staging-only project and bring it into the update cache, validated.

    Only meaningful for packaged AppImage installs; the desktop updater applies
    the staged artifact to the installed AppImage on the next launch.
    """
    manager = state.updates
    project = manager.registry.get(project_id)
    if not project or not project.staging_only:
        raise HTTPException(400, "AppImage self-update is only available for staging-only projects")
    mode = runtime_mode()
    if mode == "deb":
        raise HTTPException(400, (
            "JPNH is installed as a package; AppImage updates are not applied. "
            "Install the new JPNH release instead."))

    source = manager.source_for(project)
    if body.artifact_url or body.artifact_path is None:
        # live download from the latest release metadata (also the UI default
        # when the stage request carries an empty body)
        artifact_path, version, release_tag = _live_appimage_download(project, source)
    else:
        artifact_path = body.artifact_path
        version = None
        release_tag = None

    result = stage_appimage(manager, project, artifact_path,
                            release_tag=release_tag, version=version)
    if not result.get("ok"):
        raise HTTPException(400, result["error"])
    return {"ok": True, "project_id": project_id, "staged": result}


@updates_router.post("/{project_id}/apply-appimage")
def apply_appimage_update(project_id: str, state: AppState = Depends(get_state)):
    """Request that the staged AppImage be applied to the installed AppImage on
    the next launch. The desktop updater performs an atomic replacement.

    Only valid while running as an AppImage: a source tree cannot be replaced by
    an AppImage and a DEB install must keep using the package.
    """
    manager = state.updates
    project = manager.registry.get(project_id)
    if not project or not project.staging_only:
        raise HTTPException(400, "AppImage self-update is only available for staging-only projects")
    mode = runtime_mode()
    if mode != "appimage":
        raise HTTPException(400, (
            "JPNH is not running as an AppImage; the AppImage apply flow is only "
            "available while the installed app is the AppImage binary."))
    try:
        payload = request_appimage_apply(manager, project)
    except UpdateManagerError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "pending": payload,
            "note": "JPNH will replace the installed AppImage atomically on the next launch."}


@updates_router.post("/{project_id}/restart-apply")
def restart_apply(project_id: str, state: AppState = Depends(get_state)):
    """Request that a staged JPNH Core update be applied on the next launch.

    Only valid for staging-only projects and only in development/source mode:
    packaged AppImage/DEB installs cannot be replaced from a staged source tree
    (their resources are read-only) and are updated by installing a new JPNH
    release instead.
    """
    manager = state.updates
    project = manager.registry.get(project_id)
    if not project or not project.staging_only:
        raise HTTPException(400, "self-update is only available for staging-only projects")
    stored = manager.state.get(project_id)
    staged_path = stored.get("staged_path")
    if not staged_path:
        raise HTTPException(400, "no staged update to apply — run an update first")
    from pathlib import Path
    from ...storage.paths import update_cache_dir
    from ...updates.manager import UpdateSourceError

    staged = Path(staged_path).resolve()
    if not staged.is_dir():
        raise HTTPException(400, "staged update directory no longer exists")
    # a self-update may only apply trees the manager itself staged
    try:
        staged.relative_to(update_cache_dir().resolve())
    except ValueError:
        raise HTTPException(400, "staged update is outside the update cache") from None
    error = _validate_staged(project.required_files, project.current_version_file,
                             stored.get("staged_version"), staged)
    if error:
        raise HTTPException(400, error)

    mode = runtime_mode()
    if mode != "source":
        raise HTTPException(400, (
            "JPNH is running from a packaged build; JPNH Core is updated by "
            "installing a new JPNH release, not by replacing the source tree."))
    payload = request_apply(project_id, str(staged), stored.get("staged_version"), mode=mode)
    return {"ok": True, "pending": payload,
            "note": "JPNH will apply the staged update on the next launch."}


@updates_router.post("/pending-apply/clear")
def clear_pending(state: AppState = Depends(get_state)):
    clear_pending_apply()
    return {"ok": True}


@updates_router.post("/rollback/{backup_id}")
def rollback(backup_id: str, state: AppState = Depends(get_state)):
    try:
        return state.updates.rollback(backup_id)
    except (UpdateManagerError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc