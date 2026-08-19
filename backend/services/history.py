"""Test history storage (recent test runs, non-secret)."""

from __future__ import annotations

from typing import Optional

from ..storage.json_store import JsonStore
from ..storage.paths import history_path

MAX_HISTORY = 100


class TestHistory:
    def __init__(self, store: JsonStore | None = None):
        self._store = store or JsonStore(history_path(), [])

    def add(self, entry: dict) -> None:
        entries = self._store.read()
        if not isinstance(entries, list):
            entries = []
        entries.append(entry)
        if len(entries) > MAX_HISTORY:
            entries = entries[-MAX_HISTORY:]
        self._store.write(entries)

    def list(self, limit: int = 25) -> list[dict]:
        entries = self._store.read()
        if not isinstance(entries, list):
            return []
        return list(reversed(entries[-limit:]))
