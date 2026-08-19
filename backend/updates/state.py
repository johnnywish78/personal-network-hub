"""Persisted per-project update state (non-secret).

Stores what was last seen/installed so the Update Manager can compare across
restarts without re-downloading anything. Never stores credentials.
"""

from __future__ import annotations

from typing import Any

from ..storage.json_store import JsonStore
from ..storage.paths import update_state_path


class UpdateState:
    """JsonStore-backed map of project_id -> update metadata."""

    def __init__(self, store: JsonStore | None = None):
        self._store = store or JsonStore(update_state_path(), {})

    def _read(self) -> dict:
        data = self._store.read()
        return data if isinstance(data, dict) else {}

    def get(self, project_id: str) -> dict:
        return dict(self._read().get(project_id) or {})

    def set(self, project_id: str, **fields) -> dict:
        data = self._read()
        entry = dict(data.get(project_id) or {})
        entry.update(fields)
        data[project_id] = entry
        self._store.write(data)
        return dict(entry)

    def clear(self, project_id: str) -> None:
        data = self._read()
        if project_id in data:
            del data[project_id]
            self._store.write(data)

    def all(self) -> dict:
        return self._read()