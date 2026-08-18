"""Network Checker bundle management.

JPNH ships the ORIGINAL upstream Network Checker (mirarr-app/network-checker,
a Flutter desktop app) as a bundled third-party application. JPNH is only a
launcher/controller: it locates the bundle, reports whether it is present, and
leaves process lifecycle to the Electron host. The upstream implementation is
never rewritten or reimplemented here.

Bundle layout (packaged):
    <resources>/network-checker/<platform>/rdnbenet

Bundle layout (development):
    third_party/network-checker/build/<platform>/x64/release/bundle/rdnbenet
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path


def _project_root() -> Path:
    """Resolve the repository root when running from the source tree."""
    return Path(__file__).resolve().parents[2]


def platform_dir() -> str:
    if sys.platform.startswith("win"):
        return "win"
    if sys.platform == "darwin":
        return "mac"
    return "linux"


def _exe_name() -> str:
    return "rdnbenet.exe" if sys.platform.startswith("win") else "rdnbenet"


def bundle_path() -> Path | None:
    """Absolute path to the bundled Network Checker executable, or None."""
    if getattr(sys, "frozen", False):
        # Packaged backend lives at <resources>/backend/<platform>/jpnh-backend,
        # so the bundled app sits three parents up under network-checker/.
        exe_dir = Path(sys.executable).resolve().parent  # .../resources/backend/<platform>
        resources = exe_dir.parent.parent  # .../resources
        candidate = resources / "network-checker" / platform_dir() / _exe_name()
        if candidate.exists():
            return candidate
        return None
    # Development: run from the source tree.
    if sys.platform.startswith("win"):
        bundle = (
            _project_root()
            / "third_party"
            / "network-checker"
            / "build"
            / "windows"
            / "x64"
            / "runner"
            / "Release"
            / _exe_name()
        )
    else:
        bundle = (
            _project_root()
            / "third_party"
            / "network-checker"
            / "build"
            / platform_dir()
            / "x64"
            / "release"
            / "bundle"
            / _exe_name()
        )
    return bundle if bundle.exists() else None


def bundle_detected() -> bool:
    """Whether a usable Network Checker bundle is available."""
    return bundle_path() is not None


def env_ready() -> bool:
    """Whether a full-featured desktop session is available to run the app."""
    if sys.platform.startswith("win"):
        return bool(os.environ.get("SESSIONNAME") or os.environ.get("WINDIR"))
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


@lru_cache(maxsize=1)
def _manager_state() -> dict:
    return {"path": str(bundle_path()) if bundle_path() else None,
            "detected": bundle_detected()}


def describe() -> dict:
    return {"app": "network-checker", "bundle": platform_dir(),
            "detected": bundle_detected(), "path": str(bundle_path()) if bundle_path() else None}


@lru_cache(maxsize=1)
def network_checker_manager() -> "NetworkCheckerManager":
    return NetworkCheckerManager()


class NetworkCheckerManager:
    """Locate the bundled Network Checker app. Process lifecycle is owned by
    the Electron host, so this class only resolves/detects the bundle."""

    def bundle_detected(self) -> bool:
        return bundle_detected()

    def describe(self) -> dict:
        return describe()