"""Xray binary detection (cross-platform, never crashes)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional


def find_binary(override: Optional[str] = None) -> Optional[str]:
    """Return the xray executable path or None."""
    if override:
        return override if _binary_exists(override) else None
    for name in ("xray", "xray.exe"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _binary_exists(path: str) -> bool:
    if "/" in path or path.endswith(".exe"):
        return Path(path).expanduser().is_file()
    return shutil.which(path) is not None


def version_of(binary: str) -> Optional[str]:
    try:
        result = subprocess.run([binary, "version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            line = result.stdout.strip().splitlines()
            return line[0].split()[-1] if line else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return None
    return None


def is_running(binary: str) -> bool:
    name = Path(binary).name
    try:
        result = subprocess.run(["pgrep", "-f", name], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
