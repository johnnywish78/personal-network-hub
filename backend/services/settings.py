"""Application settings (non-secret) stored as a JSON document."""

from __future__ import annotations

from ..storage.json_store import JsonStore
from ..storage.paths import settings_path

DEFAULTS = {
    "theme": "dark",
    "client_paths": {
        "v2rayN": None,
        "hiddify": None,
        "v2box": None,
    },
    "provider_urls": {
        "bpb-worker-panel": None,
        "zeus": None,
        "rvg": None,
        "nova": None,
    },
}


class Settings:
    def __init__(self, store: JsonStore | None = None):
        self._store = store or JsonStore(settings_path(), dict(DEFAULTS))

    def _read(self) -> dict:
        data = self._store.read()
        if not isinstance(data, dict):
            return dict(DEFAULTS)
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged

    def get(self, key: str, default=None):
        data = self._read()
        keys = key.split(".")
        value = data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set(self, key: str, value) -> None:
        data = self._read()
        keys = key.split(".")
        node = data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
        self._store.write(data)

    def all(self) -> dict:
        return self._read()
