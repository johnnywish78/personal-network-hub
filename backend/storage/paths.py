"""Filesystem path resolution for JPNH local storage.

All application data lives under one data directory (default ~/.jpnh).
Secrets live in a separate file with restrictive permissions.
"""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """Resolve the application data directory."""
    env = os.environ.get("JPNH_DATA_DIR")
    if env and env.strip():
        return Path(env.strip()).expanduser()
    return Path.home() / ".jpnh"


def ensure_data_dir() -> Path:
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def configs_path() -> Path:
    return ensure_data_dir() / "configs.json"


def providers_path() -> Path:
    return ensure_data_dir() / "providers.json"


def settings_path() -> Path:
    return ensure_data_dir() / "settings.json"


def secrets_path() -> Path:
    return ensure_data_dir() / "secrets.json"


def history_path() -> Path:
    return ensure_data_dir() / "test_history.json"


def services_path() -> Path:
    return ensure_data_dir() / "services.json"


def favorites_path() -> Path:
    return ensure_data_dir() / "favorites.json"


def log_entries_path() -> Path:
    return ensure_data_dir() / "logs.json"


def logs_path() -> Path:
    return ensure_data_dir() / "logs"


def backups_dir() -> Path:
    d = ensure_data_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def projects_dir() -> Path:
    d = ensure_data_dir() / "projects"
    d.mkdir(parents=True, exist_ok=True)
    return d


def update_cache_dir() -> Path:
    d = ensure_data_dir() / "update-cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def update_state_path() -> Path:
    return ensure_data_dir() / "updates.json"


def update_history_path() -> Path:
    return ensure_data_dir() / "update_history.json"
