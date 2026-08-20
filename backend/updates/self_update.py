"""JPNH self-update — apply a staged JPNH Core update on the next launch.

The running JPNH checkout is never replaced in place (``staging_only``). A
staged update is validated and held in the update cache, then a "pending apply"
marker records that it should be applied the next time the application starts.
The external updater (the desktop host) or the ``apply_pending`` CLI consumes
that marker before the new instance begins serving.

Safety guarantees enforced here:

* the staged tree is validated (required files + version consistency) before
  anything on disk is touched
* the current tree is moved to a recoverable rollback directory before the
  staged tree is swapped in — never deleted first
* a health check runs after the swap; on failure the previous tree is restored
* for AppImage/DEB installations the source tree cannot be swapped (the app
  runs from a read-only bundle) — the pending marker records the downloaded
  artifact instead, and the desktop host performs an atomic file replacement
* the marker is removed only after a successful apply
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from ..storage.paths import ensure_data_dir, pending_apply_path, update_cache_dir
from .health import HealthCheckManager
from .history import UpdateHistory
from .manager import METADATA_FILE, UpdateManager
from .sources import parse_version_from_file, UpdateSourceError
from .state import UpdateState

# Keep in sync with the desktop updater (desktop/lib/self-updater.js).
PENDING_APPLY_FILE = "pending-apply.json"
PENDING_APPLY_EXCLUDES = {"build", "dist", "node_modules", ".venv", "venv",
                          ".git", "__pycache__", "resources/backend",
                          "resources/network-checker"}


def runtime_mode() -> str:
    """Detect how JPNH is running: ``source``, ``appimage``, ``deb``,
    ``bundled`` or ``unknown``.

    ``appimage`` requires the ``APPIMAGE`` environment variable that Electron
    sets for AppImage builds. ``deb`` is detected from the installation
    prefix. Everything frozen-but-not-AppImage is ``bundled``.
    """
    if not getattr(sys, "frozen", False):
        return "source"
    appimage = os.environ.get("APPIMAGE")
    if appimage:
        return "appimage"
    exe = Path(sys.executable).resolve()
    if "opt" in exe.parts or "usr" in exe.parts:
        return "deb"
    return "bundled"


def appimage_target() -> Optional[str]:
    """Absolute path of the running AppImage, when running as one."""
    return os.environ.get("APPIMAGE")


def pending_apply_info() -> Optional[dict]:
    """Read the pending-apply marker, or None when there is none."""
    path = pending_apply_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def request_apply(project_id: str, staged_path: str, expected_version: Any = None,
                  mode: Optional[str] = None, appimage_artifact: Optional[str] = None) -> dict:
    """Write the pending-apply marker for a validated staged update."""
    payload = {
        "project_id": project_id,
        "staged_path": staged_path,
        "expected_version": str(expected_version) if expected_version is not None else None,
        "requested_at": _now_iso(),
        "mode": mode or runtime_mode(),
        "appimage_artifact": appimage_artifact,
    }
    path = pending_apply_path()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def clear_pending_apply() -> None:
    path = pending_apply_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# AppImage self-update helpers
# ---------------------------------------------------------------------------

APPIMAGE_MAGIC = b"\x7fELF"
APPIMAGE_TYPE1 = b"\x41\x49\x01"  # "AI" + type byte (ISO9660)
APPIMAGE_TYPE2 = b"\x41\x49\x02"  # "AI" + type byte (squashfs)
MIN_APPIMAGE_BYTES = 1024 * 1024


def find_appimage_asset(available: Optional[dict]) -> Optional[dict]:
    """Pick the AppImage asset from a release's assets, preferring the one
    that matches the release version. Returns None when there is none."""
    if not available:
        return None
    assets = [a for a in (available.get("assets") or [])
              if str(a.get("name", "")).lower().endswith(".appimage")]
    if not assets:
        return None
    version = available.get("version")
    if version:
        ver = str(version)
        for asset in assets:
            if ver in asset.get("name", ""):
                return asset
    return assets[0]


def sha256_file(path: Any) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_appimage_artifact(path: Any) -> Optional[str]:
    """Return an error message when ``path`` is not a usable AppImage, else None."""
    p = Path(path)
    if not p.exists():
        return "AppImage artifact does not exist"
    if not p.is_file():
        return "AppImage artifact is not a file"
    if p.stat().st_size < MIN_APPIMAGE_BYTES:
        return "AppImage artifact is too small to be a real AppImage"
    try:
        head = p.open("rb").read(4096)
    except OSError as exc:
        return f"AppImage artifact is unreadable: {exc}"
    if not head.startswith(APPIMAGE_MAGIC):
        return "artifact is not an ELF executable"
    # canonical AppImage magic: "AI" at offset 8 with the type byte
    if not (head[8:11] == APPIMAGE_TYPE1 or head[8:11] == APPIMAGE_TYPE2):
        return "artifact is not an AppImage"
    if not os.access(p, os.X_OK):
        return "AppImage artifact is not executable"
    return None


def stage_appimage(manager: UpdateManager, project: ProjectManifest,
                   artifact_path: Any, *, release_tag: Any = None,
                   version: Any = None) -> dict:
    """Bring a validated AppImage artifact into the update cache and record it
    in the project state as the staged AppImage update.

    Returns ``{"ok": True, "artifact": <path>, "sha256": <hex>, "version": ...}``
    or ``{"ok": False, "error": <message>}``. Never raises.
    """
    src = Path(artifact_path).resolve()
    if not src.exists():
        return {"ok": False, "error": f"AppImage artifact not found: {src}"}
    error = validate_appimage_artifact(src)
    if error:
        return {"ok": False, "error": error}

    cache = update_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    stamp = _now_compact()
    dest = cache / f"{project.id}-appimage-{release_tag or version or stamp}.AppImage"
    try:
        shutil.copy2(str(src), str(dest))
        os.chmod(dest, 0o755)
    except OSError as exc:
        return {"ok": False, "error": f"could not stage AppImage artifact: {exc}"}

    checksum = sha256_file(dest)
    manager.state.set(project.id,
                      staged_artifact=str(dest), staged_artifact_sha256=checksum,
                      staged_release_tag=str(release_tag) if release_tag else None,
                      staged_version=str(version) if version else None,
                      updated_at=_now_iso(), last_check=_now_iso(), last_error=None)
    manager._log_ok(f"{project.id}: staged AppImage {dest.name} ({checksum})")
    return {"ok": True, "artifact": str(dest), "sha256": checksum,
            "version": version, "release_tag": release_tag}


def request_appimage_apply(manager: UpdateManager, project: ProjectManifest) -> dict:
    """Write the pending-apply marker for a previously staged AppImage update.

    Only valid when the manager has a staged AppImage artifact inside the
    update cache. Returns the marker payload; raises UpdateManagerError on
    any invalid state.
    """
    stored = manager.state.get(project.id)
    artifact = stored.get("staged_artifact")
    if not artifact:
        raise UpdateManagerError("no staged AppImage update — download it first")
    staged = Path(artifact).resolve()
    cache = update_cache_dir().resolve()
    try:
        staged.relative_to(cache)
    except ValueError:
        raise UpdateManagerError("staged AppImage is outside the update cache") from None
    if not staged.exists():
        raise UpdateManagerError("staged AppImage no longer exists")
    error = validate_appimage_artifact(staged)
    if error:
        raise UpdateManagerError(error)
    payload = request_apply(project.id, None, stored.get("staged_version"),
                            mode="appimage",
                            appimage_artifact=str(staged))
    payload["sha256"] = stored.get("staged_artifact_sha256") or sha256_file(staged)
    payload["release_tag"] = stored.get("staged_release_tag")
    payload["target"] = resolve_appimage_target()
    pending_apply_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def resolve_appimage_target() -> Optional[str]:
    """Resolve the installed AppImage that the desktop launcher runs.

    Priority: the running AppImage (``APPIMAGE`` env), then the Exec= target
    of the per-user desktop entry. Returns an absolute path or None. This is
    the backend mirror of the desktop updater's resolution; it never guesses
    and never hard-codes a home directory.
    """
    env_path = os.environ.get("APPIMAGE")
    if env_path and Path(env_path).is_file():
        return str(Path(env_path).resolve())
    home = os.path.expanduser("~")
    entry = Path(home) / ".local/share/applications/jpnh.desktop"
    if not entry.is_file():
        return None
    try:
        text = entry.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("Exec="):
            for token in line[5:].split():
                tok = token.strip('"')
                if tok.lower().endswith(".appimage") and Path(tok).is_file():
                    return str(Path(tok).resolve())
    return None


def _staged_dir(marker: dict) -> Optional[Path]:
    staged = marker.get("staged_path")
    if not staged:
        return None
    path = Path(staged).resolve()
    return path if path.is_dir() else None


def _validate_staged(required_files: list[str], version_file: Optional[str],
                     expected_version: Any, staged: Path) -> Optional[str]:
    """Returns an error message when the staged tree is unusable, else None."""
    for rel in required_files:
        if not (staged / rel).exists():
            return f"staged update is missing required file: {rel}"
    if version_file:
        found = parse_version_from_file(staged / version_file)
        if expected_version and found and str(expected_version) != str(found):
            return f"staged version mismatch: expected {expected_version}, found {found}"
    return None


def apply_staged_source(manager: UpdateManager, marker: dict) -> dict:
    """Swap the staged source tree into the repository root with a full backup
    and automatic rollback. Never raises: failures are returned as dicts.

    Intended to run at application startup, from the external updater or the
    ``apply_pending`` CLI. The running process continues on the old code; the
    new tree takes effect on the following launch.
    """
    project = manager.registry.get(marker.get("project_id", ""))
    if not project:
        return {"ok": False, "error": f"unknown project {marker.get('project_id')}"}
    staged = _staged_dir(marker)
    if not staged:
        return {"ok": False, "error": "staged path is missing or invalid"}

    # Safety: the external updater may only apply trees that the Update Manager
    # itself staged into the update cache. A marker pointing anywhere else is
    # treated as corrupt and never acted upon.
    cache = update_cache_dir().resolve()
    try:
        staged.relative_to(cache)
    except ValueError:
        return {"ok": False, "error": f"staged path is outside the update cache: {staged}"}

    root = manager.root.resolve()
    if project.install_path not in (None, "", "."):
        return {"ok": False, "error": "self-update only applies to the repository root"}

    error = _validate_staged(project.required_files, project.current_version_file,
                             marker.get("expected_version"), staged)
    if error:
        return {"ok": False, "error": error}

    # a backup of the current tree goes to a dedicated rollback directory so
    # the swap can always be undone even if state/history are lost
    rollback_dir = ensure_data_dir() / "self-update-rollback"
    stamp = _now_compact()
    current_backup = rollback_dir / f"pre-{project.id}-{stamp}"
    current_backup.parent.mkdir(parents=True, exist_ok=True)

    try:
        manager._log_info(f"applying self-update {marker.get('expected_version')} -> {root}")
        if root.exists():
            shutil.move(str(root), str(current_backup))
        root.mkdir(parents=True)
        for item in staged.iterdir():
            shutil.move(str(item), str(root / item.name))
    except OSError as exc:
        manager._log_err(f"self-update apply failed: {exc}")
        _restore_tree(root, current_backup)
        return {"ok": False, "error": f"swap failed: {exc}", "backup": str(current_backup)}

    # validate the applied tree and roll back on any health failure
    health = manager.health.run(project, backend_alive=True,
                                expected_version=marker.get("expected_version"))
    ok = bool(health.get("ok"))
    if not ok:
        manager._log_err(f"self-update health check failed: {health}")
        _restore_tree(root, current_backup)
        return {"ok": False, "error": f"health check failed after apply: {health}",
                "backup": str(current_backup)}

    new_version = marker.get("expected_version") or (
        parse_version_from_file(root / project.current_version_file)
        if project.current_version_file else None)
    manager.history.add({
        "project": project.id,
        "old_version": None,
        "new_version": new_version,
        "result": "applied-on-restart",
        "backup_id": None,
        "rollback_status": "ok",
        "build_result": {"ran": False, "detail": "self-update (no build)"},
        "health_result": {"ok": True, "checks": health.get("checks", [])},
    })
    manager.state.set(project.id,
                      staged_ref=None, staged_version=None, staged_path=None,
                      installed_ref=marker.get("expected_version") or new_version,
                      installed_version=new_version,
                      installed_fingerprint=None,
                      updated_at=_now_iso(), last_check=_now_iso(), last_error=None)
    clear_pending_apply()
    manager._log_ok(f"self-update applied (version {new_version}); rollback saved at {current_backup}")
    return {"ok": True, "new_version": new_version, "backup": str(current_backup),
            "health": health}


def _restore_tree(root: Path, backup: Path) -> None:
    """Restore a previously moved tree; used on apply failure."""
    try:
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        if backup.exists():
            shutil.move(str(backup), str(root))
    except OSError:
        pass


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _now_compact() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S%f")


__all__ = ["runtime_mode", "appimage_target", "pending_apply_info", "request_apply",
           "clear_pending_apply", "apply_staged_source", "find_appimage_asset",
           "validate_appimage_artifact", "stage_appimage", "request_appimage_apply",
           "resolve_appimage_target", "sha256_file"]
