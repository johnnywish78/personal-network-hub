"""Robust version resolution for both source and PyInstaller-packaged runs.

When the backend is bundled with PyInstaller, ``__file__`` no longer points
at the project checkout, so VERSION must be resolved from the frozen bundle
root (``sys._MEIPASS``) instead of walking the source tree.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _bundle_root() -> Path:
    """Return the directory that contains the bundled VERSION file."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def get_version() -> str:
    return (_bundle_root() / "VERSION").read_text(encoding="utf-8").strip()