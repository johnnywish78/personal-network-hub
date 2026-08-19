"""Update history storage (non-secret, mirrors TestHistory conventions).

Each entry records: timestamp, project, old/new version, result, error,
backup id, and rollback status. Never stores tokens, passwords, or secrets.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Optional

from ..storage.json_store import JsonStore
from ..storage.paths import update_history_path

MAX_HISTORY = 200


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def new_history_id() -> str:
    return uuid.uuid4().hex[:12]


class UpdateHistory:
    def __init__(self, store: JsonStore | None = None):
        self._store = store or JsonStore(update_history_path(), [])

    def add(self, entry: dict[str, Any]) -> dict[str, Any]:
        record = {
            "id": new_history_id(),
            "timestamp": utc_now_iso(),
            "project": str(entry.get("project") or "unknown"),
            "old_version": entry.get("old_version"),
            "new_version": entry.get("new_version"),
            "result": str(entry.get("result") or "unknown"),   # staged | success | failed | rolled-back | skipped
            "error": entry.get("error"),
            "backup_id": entry.get("backup_id"),
            "rollback_status": entry.get("rollback_status"),
        }
        entries = self._store.read()
        if not isinstance(entries, list):
            entries = []
        entries.append(record)
        if len(entries) > MAX_HISTORY:
            entries = entries[-MAX_HISTORY:]
        self._store.write(entries)
        return record

    def list(self, limit: int = 50, project: Optional[str] = None) -> list[dict]:
        entries = self._store.read()
        if not isinstance(entries, list):
            return []
        if project:
            entries = [e for e in entries if e.get("project") == project]
        return list(reversed(entries[-limit:]))

    def get(self, history_id: str) -> Optional[dict]:
        for entry in self._store.read():
            if entry.get("id") == history_id:
                return entry
        return None