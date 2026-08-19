"""Health Check Manager — post-update verification.

Reuses existing JPNH diagnostics where they exist (backend API reachability,
bundled Network Checker detection) instead of duplicating logic. Each project
declares which checks apply in its manifest's ``health_checks`` list.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from ..services.network_checker import bundle_detected
from ..version import get_version
from .manifest import ProjectManifest

KNOWN_CHECKS = {"backend-api", "version-consistency", "required-files",
                "network-checker-bundle", "install-exists"}


class HealthCheckManager:
    """Runs per-project health checks and aggregates results."""

    def __init__(self, root: Optional[Path] = None):
        self._root = root or Path(__file__).resolve().parents[2]

    def supported(self) -> list[str]:
        return sorted(KNOWN_CHECKS)

    def run(self, project: ProjectManifest, *, backend_alive: bool = True,
            **context) -> dict[str, Any]:
        """Run the project's declared health checks.

        Returns ``{"ok": bool, "checks": [ {name, ok, detail} ... ]}``.
        """
        checks = []
        for name in project.health_checks:
            if name not in KNOWN_CHECKS:
                checks.append({"name": name, "ok": False, "detail": "unknown health check"})
                continue
            ok, detail = self._run_one(project, name, backend_alive=backend_alive, **context)
            checks.append({"name": name, "ok": ok, "detail": detail})
        return {"ok": all(c["ok"] for c in checks), "checks": checks}

    def _run_one(self, project: ProjectManifest, name: str, *, backend_alive: bool,
                 **context) -> tuple[bool, str]:
        if name == "backend-api":
            return backend_alive, ("backend responded" if backend_alive
                                   else "backend did not respond")
        if name == "version-consistency":
            version_file = project.install_dir(self._root) / (project.current_version_file or "VERSION")
            if not version_file.exists():
                return False, f"version file missing: {project.current_version_file or 'VERSION'}"
            from .sources import parse_version_from_file
            local = parse_version_from_file(version_file)
            expected = context.get("expected_version")
            if expected and local and local != str(expected):
                return False, f"version mismatch: local {local} != expected {expected}"
            return local is not None, f"version file readable: {local}"
        if name == "required-files":
            missing = []
            install_dir = project.install_dir(self._root)
            for rel in project.required_files:
                if not (install_dir / rel).exists():
                    missing.append(rel)
            if missing:
                return False, f"missing files: {', '.join(missing)}"
            return True, "required files present"
        if name == "network-checker-bundle":
            try:
                found = bundle_detected()
            except Exception:  # pragma: no cover - defensive
                found = False
            return found, ("bundle detected" if found else "Network Checker bundle not found")
        if name == "install-exists":
            install_dir = project.install_dir(self._root)
            ok = install_dir.exists() and any(install_dir.iterdir())
            return ok, (f"install directory present: {install_dir}" if ok
                        else f"install directory missing: {install_dir}")
        return False, "unhandled check"


def backend_api_alive(timeout: float = 3.0) -> bool:
    """Check whether the current backend process can answer a request."""
    try:
        import httpx
        resp = httpx.get(f"http://127.0.0.1:{_backend_port()}", timeout=timeout)
        return resp.status_code < 500
    except Exception:
        return False


def _backend_port() -> int:
    import os
    return int(os.environ.get("JPNH_BACKEND_PORT", "8765"))


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def current_jpnh_version() -> str:
    try:
        return get_version()
    except Exception:
        return "0.0.0"