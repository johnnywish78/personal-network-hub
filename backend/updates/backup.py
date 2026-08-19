"""Backup Manager — recoverable snapshots before every update.

Backups live under ``<data_dir>/backups/<project>-<timestamp>/`` and contain:

* ``manifest.json``  — backup metadata (id, project, times, result)
* ``metadata.json``  — the project manifest + installed version info
* ``state/``         — user state files (settings, services, configs,
                       history, logs). Secret *values* are never copied;
                       only credential key names are recorded.
* ``project/``       — copy of the project's install directory
                       (generated/build artifacts excluded).

Backups are local application data. Nothing here writes to git, and secrets
never appear in the backup metadata or logs.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

from ..storage.paths import (backups_dir, configs_path, history_path,
                             log_entries_path, services_path, settings_path)
from .manifest import ProjectManifest

_BACKUP_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*-[0-9TZ:.-]+$")

BACKUP_EXCLUDE = {
    "build", ".dart_tool", ".git", ".flutter-plugins-dependencies",
    "node_modules", "dist", ".venv", "venv", "__pycache__",
    ".jpnh-update.json",
}


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _timestamp_safe() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def validate_backup_id(backup_id: str) -> str:
    backup_id = str(backup_id or "").strip()
    if not _BACKUP_ID_RE.match(backup_id) or ".." in backup_id:
        raise ValueError("invalid backup id")
    return backup_id


# State files that should always be snapshotted before an update.
STATE_FILES = {
    "settings": settings_path,
    "services": services_path,
    "configs": configs_path,
    "test_history": history_path,
    "logs": log_entries_path,
}


class BackupManager:
    def __init__(self, root: Optional[Path] = None):
        self._root = root or _project_root()

    def create(self, project: ProjectManifest, *, version_info: Optional[dict] = None,
               credential_keys: Optional[list[str]] = None) -> str:
        """Create a backup for a project; returns the backup id."""
        project_dir = project.install_dir(self._root)
        backup_id = f"{project.id}-{_timestamp_safe()}"
        backup_root = backups_dir() / backup_id
        backup_root.mkdir(parents=True, exist_ok=False)

        try:
            manifest = {
                "backup_id": backup_id,
                "project": project.id,
                "created_at": utc_now_iso(),
                "tool": "jpnh-update-manager",
            }
            _write_json(backup_root / "manifest.json", manifest)

            metadata = {
                "project": project.to_dict(),
                "version_info": version_info or {},
                "credential_keys": sorted(credential_keys or []),
            }
            _write_json(backup_root / "metadata.json", metadata)

            state_dir = backup_root / "state"
            for name, path_fn in STATE_FILES.items():
                path = path_fn()
                if path.exists():
                    shutil.copy2(path, state_dir / f"{name}.json")

            if project.install_path and project_dir.exists():
                dest = backup_root / "project"
                _copy_tree(project_dir, dest, project.exclude_backup)
        except BaseException:
            shutil.rmtree(backup_root, ignore_errors=True)
            raise
        return backup_id

    # -- listing / lookup ------------------------------------------------------

    def list(self, project: Optional[str] = None) -> list[dict]:
        out = []
        base = backups_dir()
        if not base.exists():
            return out
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            meta = _read_json(child / "manifest.json")
            if meta is None:
                continue
            if project and meta.get("project") != project:
                continue
            out.append({
                "backup_id": meta.get("backup_id") or child.name,
                "project": meta.get("project"),
                "created_at": meta.get("created_at"),
                "path": str(child),
            })
        return sorted(out, key=lambda b: b.get("created_at") or "", reverse=True)

    def get(self, backup_id: str) -> Optional[dict]:
        validate_backup_id(backup_id)
        base = backups_dir() / backup_id
        if not base.exists():
            return None
        meta = _read_json(base / "manifest.json")
        if meta is None:
            return None
        return {**meta, "path": str(base)}

    def resolve(self, backup_id: str) -> Path:
        validate_backup_id(backup_id)
        base = backups_dir() / backup_id
        if not base.exists():
            raise FileNotFoundError(f"backup not found: {backup_id}")
        return base

    def delete(self, backup_id: str) -> bool:
        validate_backup_id(backup_id)
        base = backups_dir() / backup_id
        if not base.exists():
            return False
        shutil.rmtree(base, ignore_errors=True)
        return not base.exists()

    # -- restore ----------------------------------------------------------------

    def restore(self, backup_id: str, project: ProjectManifest) -> dict:
        """Restore a project + user state from a backup.

        Returns ``{"project_restored": bool, "state_restored": [...], ...}``.
        """
        backup_root = self.resolve(backup_id)

        project_dir = project.install_dir(self._root)
        project_restored = False
        project_src = backup_root / "project"
        if project_src.exists():
            if project_dir.exists():
                shutil.rmtree(project_dir)
            project_dir.mkdir(parents=True, exist_ok=True)
            _copy_tree(project_src, project_dir, project.exclude_backup)
            project_restored = True

        state_restored = []
        state_dir = backup_root / "state"
        if state_dir.exists():
            for name, path_fn in STATE_FILES.items():
                src = state_dir / f"{name}.json"
                if src.exists():
                    path = path_fn()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, path)
                    state_restored.append(name)

        metadata = _read_json(backup_root / "metadata.json") or {}
        return {
            "backup_id": backup_id,
            "project": project.id,
            "project_restored": project_restored,
            "state_restored": state_restored,
            "metadata": metadata,
        }


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _read_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _copy_tree(src: Path, dest: Path, exclude: Optional[list[str]] = None) -> None:
    """Copy a tree, skipping generated/build directories."""
    excludes = set(BACKUP_EXCLUDE)
    if exclude:
        excludes.update(str(e).strip("/") for e in exclude)
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in excludes:
            continue
        target = dest / item.name
        if item.is_dir():
            _copy_tree(item, target, list(excludes))
        else:
            try:
                shutil.copy2(item, target)
            except OSError:
                continue