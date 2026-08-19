"""Detect installed client applications (v2rayN, Hiddify, V2Box).

These remain external; the Hub only detects them to offer hand-off
actions. Detection uses PATH lookup, common install directories, and any
user-configured paths in settings.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

CLIENTS = [
    {"id": "v2rayN", "names": ["v2rayN", "v2rayN.exe", "v2rayn"], "hint": "Windows client"},
    {"id": "hiddify", "names": ["Hiddify", "hiddify", "HiddifyDesktop", "hiddify-cli"], "hint": "Cross-platform client"},
    {"id": "v2box", "names": ["v2box", "V2Box", "v2box.app"], "hint": "Android/mobile client"},
]

COMMON_DIRS = [
    Path.home() / "AppData" / "Local",
    Path.home() / "AppData" / "Roaming",
    Path("/opt"),
    Path("/usr/local/bin"),
    Path.home(),
]


def detect_clients(user_paths: Optional[dict] = None) -> list[dict]:
    """Return a list of client detection results."""
    user_paths = user_paths or {}
    results = []
    for client in CLIENTS:
        path = _find_client(client["names"], user_paths.get(client["id"]))
        results.append({
            "id": client["id"],
            "name": client["id"],
            "hint": client["hint"],
            "detected": path is not None,
            "path": path,
        })
    return results


def _find_client(names: list[str], configured: Optional[str]) -> Optional[str]:
    if configured:
        p = Path(configured).expanduser()
        if p.exists():
            return str(p)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    # Best-effort scan of common directories (top level only, no deep walk).
    for directory in COMMON_DIRS:
        if not directory.exists():
            continue
        try:
            for child in directory.iterdir():
                if child.name in names or child.name.lower() in [n.lower() for n in names]:
                    if child.is_file() and os.access(child, os.X_OK):
                        return str(child)
        except PermissionError:
            continue
    return None
