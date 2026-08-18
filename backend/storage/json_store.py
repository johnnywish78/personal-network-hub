"""Small, dependency-free JSON-backed store with atomic writes and locking.

Used for configs, providers, settings, and test history.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

_lock = threading.RLock()


def load_json(path: Path, default: Any) -> Any:
    """Load JSON from file, returning `default` if missing/invalid."""
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: Path, data: Any) -> None:
    """Atomically write JSON to `path` (write temp file then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


class JsonStore:
    """Thread-safe JSON document store backed by a single file."""

    def __init__(self, path: Path, default: Any):
        self._path = path
        self._default = default

    def read(self) -> Any:
        with _lock:
            return load_json(self._path, self._default)

    def write(self, data: Any) -> None:
        save_json(self._path, data)

    def path(self) -> Path:
        return self._path
