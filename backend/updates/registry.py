"""Project/Component Registry — the source of truth for what can be updated.

Built-in projects are defined here in one place. Additional managed projects
can be added without touching core code by dropping a JSON manifest in the
per-user projects directory (``<data_dir>/projects/<id>.json``), or by
registering a :class:`ProjectManifest` in code.

Only manifests that pass strict validation are loaded; malformed files are
skipped and reported instead of crashing the registry.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from ..storage.json_store import load_json
from ..storage.paths import projects_dir
from .manifest import ProjectManifest

# ---------------------------------------------------------------------------
# Built-in registry (single source of truth)
# ---------------------------------------------------------------------------

BUILTIN_PROJECTS: list[dict[str, Any]] = [
    {
        "id": "jpnh-core",
        "name": "JPNH Core",
        "description": "Johnny Personal Network Hub itself.",
        "category": "core",
        "icon": "▦",
        "enabled": True,
        "source_type": "github",
        "repository": "johnnywish78/personal-network-hub",
        "branch": "main",
        "install_path": ".",
        "update_strategy": "download",
        "build_strategy": "none",
        "version_detection": "version_file",
        "current_version_file": "VERSION",
        "release_only": True,
        "staging_only": True,   # never swap the running checkout in place
        "health_checks": ["backend-api", "version-consistency"],
        "required_files": ["VERSION", "backend/main.py"],
    },
    {
        "id": "network-checker",
        "name": "Network Checker",
        "description": "Upstream mirarr-app/network-checker Flutter app (GPL-3.0), vendored under third_party/.",
        "category": "tools",
        "icon": "⛨",
        "enabled": True,
        "source_type": "github",
        "repository": "mirarr-app/network-checker",
        "branch": "main",
        "install_path": "third_party/network-checker",
        "update_strategy": "download",
        "build_strategy": "network-checker",
        "version_detection": "file",
        "current_version_file": "pubspec.yaml",
        "rollback_strategy": "backup",
        "exclude_backup": ["build", ".dart_tool", ".git", ".flutter-plugins-dependencies"],
        "health_checks": ["required-files", "network-checker-bundle"],
        "required_files": ["pubspec.yaml", "lib/main.dart"],
    },
]


class ProjectRegistry:
    """Loads and resolves project manifests (built-in + per-user files)."""

    def __init__(self, user_dir=None):
        self._user_dir = user_dir or projects_dir()
        self._overrides: dict[str, ProjectManifest] = {}
        self._errors: list[str] = []

    # -- registration --------------------------------------------------------

    def register(self, manifest: ProjectManifest) -> None:
        """Register a project manifest at runtime (code-driven addition)."""
        manifest.validate()
        self._overrides[manifest.id] = manifest

    def unregister(self, project_id: str) -> bool:
        return self._overrides.pop(project_id, None) is not None

    def errors(self) -> list[str]:
        """User-manifest load errors (never raised; surfaced to the UI)."""
        return list(self._errors)

    # -- loading -------------------------------------------------------------

    def _user_manifests(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        self._errors = []
        if not self._user_dir.exists():
            return entries
        for path in sorted(self._user_dir.glob("*.json")):
            data = load_json(path, None)
            if not isinstance(data, dict):
                self._errors.append(f"{path.name}: not a JSON object")
                continue
            data.setdefault("id", path.stem)
            entries.append(data)
        return entries

    def list(self) -> list[ProjectManifest]:
        """All project manifests (built-ins + user files), validated.

        A malformed user manifest is skipped and reported via ``errors()`` so
        one bad file can never break the registry or the UI.
        """
        manifests: dict[str, ProjectManifest] = {}
        builtin_ids: set[str] = set()
        for raw in BUILTIN_PROJECTS:
            try:
                manifest = ProjectManifest.from_dict(raw)
                manifest.validate()
                manifests[manifest.id] = manifest
                builtin_ids.add(manifest.id)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"invalid built-in project '{raw.get('id')}': {exc}") from exc
        for raw in self._user_manifests():
            try:
                manifest = ProjectManifest.from_dict(raw, strict=True)
                manifest.validate()
                if manifest.id in builtin_ids:
                    # a per-user file must never override a built-in project;
                    # that would let a stray manifest redirect the vendored
                    # Network Checker or JPNH core to an arbitrary repository
                    self._errors.append(f"{raw.get('id')}: cannot override built-in project '{manifest.id}'")
                    continue
                manifests[manifest.id] = manifest
            except (ValueError, TypeError) as exc:
                self._errors.append(f"{raw.get('id')}: {exc}")
        for manifest in self._overrides.values():
            manifests[manifest.id] = manifest
        return [manifests[pid] for pid in sorted(manifests)]

    def get(self, project_id: str) -> Optional[ProjectManifest]:
        for manifest in self.list():
            if manifest.id == project_id:
                return manifest
        return None

    def ids(self) -> list[str]:
        return [m.id for m in self.list()]

    def describe(self) -> list[dict]:
        return [m.to_dict() for m in self.list()]


def build_registry() -> ProjectRegistry:
    return ProjectRegistry()


_loaded: Optional[ProjectRegistry] = None


def default_registry() -> ProjectRegistry:
    """Process-wide singleton registry."""
    global _loaded
    if _loaded is None:
        _loaded = build_registry()
    return _loaded