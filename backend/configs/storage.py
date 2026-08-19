"""Persistent storage for saved configurations.

Configs are stored as a JSON document. The stored representation keeps the
full normalized fields plus `raw_config`, so the original is never lost.
"""

from __future__ import annotations

from typing import Optional

from ..storage.json_store import JsonStore
from ..storage.paths import configs_path
from .model import ConfigStatus, NormalizedConfig
from .normalizer import utc_now_iso


class ConfigStore:
    def __init__(self, store: Optional[JsonStore] = None):
        self._store = store or JsonStore(configs_path(), [])

    def _read(self) -> list[dict]:
        data = self._store.read()
        return data if isinstance(data, list) else []

    def list(self) -> list[NormalizedConfig]:
        return [NormalizedConfig(**item) for item in self._read()]

    def get(self, config_id: str) -> Optional[NormalizedConfig]:
        for item in self._read():
            if item.get("id") == config_id:
                return NormalizedConfig(**item)
        return None

    def save(self, config: NormalizedConfig) -> NormalizedConfig:
        items = self._read()
        for i, item in enumerate(items):
            if item.get("id") == config.id:
                config.updated_at = utc_now_iso()
                items[i] = config.model_dump(mode="json")
                self._store.write(items)
                return config
        items.append(config.model_dump(mode="json"))
        self._store.write(items)
        return config

    def add_many(self, configs: list[NormalizedConfig]) -> list[NormalizedConfig]:
        items = self._read()
        existing = {item.get("id") for item in items}
        added: list[NormalizedConfig] = []
        for cfg in configs:
            if cfg.id in existing:
                continue
            items.append(cfg.model_dump(mode="json"))
            existing.add(cfg.id)
            added.append(cfg)
        self._store.write(items)
        return added

    def update_status(self, config_id: str, status: ConfigStatus, latency_ms: Optional[float] = None,
                      error: Optional[str] = None) -> Optional[NormalizedConfig]:
        items = self._read()
        for item in items:
            if item.get("id") == config_id:
                item["status"] = status.value
                item["last_tested_at"] = utc_now_iso()
                if latency_ms is not None:
                    item["latency_ms"] = latency_ms
                if error is not None:
                    item["error"] = error
                self._store.write(items)
                return NormalizedConfig(**item)
        return None

    def update(self, config_id: str, **fields) -> Optional[NormalizedConfig]:
        """Patch metadata fields (name, tags, group, provider, ...)."""
        items = self._read()
        for item in items:
            if item.get("id") == config_id:
                for key, value in fields.items():
                    if key == "tags":
                        if isinstance(value, str):
                            value = [t.strip() for t in value.split(",") if t.strip()]
                        item[key] = value
                    elif key in ("name", "group", "provider", "address", "port"):
                        item[key] = value
                    else:
                        item[key] = value
                item["updated_at"] = utc_now_iso()
                self._store.write(items)
                return NormalizedConfig(**item)
        return None

    def duplicate(self, config_id: str, new_name: Optional[str] = None) -> Optional[NormalizedConfig]:
        """Clone a config with a new id, preserving the raw original."""
        cfg = self.get(config_id)
        if not cfg:
            return None
        import uuid as uuidlib
        clone = cfg.model_copy(deep=True)
        clone.id = uuidlib.uuid4().hex[:12]
        clone.name = new_name or f"{cfg.name} (copy)"
        clone.status = ConfigStatus.UNKNOWN
        clone.latency_ms = None
        clone.error = None
        clone.last_tested_at = None
        clone.created_at = utc_now_iso()
        clone.updated_at = utc_now_iso()
        return self.save(clone)

    def delete(self, config_id: str) -> bool:
        items = self._read()
        remaining = [item for item in items if item.get("id") != config_id]
        if len(remaining) == len(items):
            return False
        self._store.write(remaining)
        return True

    def counts(self) -> dict:
        items = self._read()
        counts = {"total": len(items), "working": 0, "testing": 0, "failed": 0,
                  "degraded": 0, "unknown": 0}
        for item in items:
            status = str(item.get("status", "UNKNOWN")).lower()
            counts[status] = counts.get(status, 0) + 1
        return counts
