"""Service Registry.

Every integrated service has a standard definition:

    id, name, type, url, icon, category, enabled, status,
    open_mode, integration_type

Presets cover the built-in services; users can add/remove services without
changing core code. User additions and disabled presets are persisted in
services.json. Status is computed live from the relevant adapter/API.
"""

from __future__ import annotations

from typing import Any, Optional

from ..providers.github.client import DEFAULT_REPOS
from ..storage.json_store import JsonStore
from ..storage.paths import services_path

# open_mode: embedded (Browser Hub) | external (system browser) | api | launcher
# type:      panel | dashboard | repo | tool | runtime | provider | checker

PRESET_SERVICES: list[dict[str, Any]] = [
    {"id": "github", "name": "GitHub", "type": "dashboard", "url": "https://github.com",
     "icon": "⌥", "category": "source", "open_mode": "embedded", "integration_type": "api_client",
     "repo": None},
    {"id": "cloudflare", "name": "Cloudflare", "type": "dashboard", "url": "https://dash.cloudflare.com",
     "icon": "☁", "category": "cloud", "open_mode": "embedded", "integration_type": "api_client",
     "repo": None},
    {"id": "railway", "name": "Railway", "type": "dashboard", "url": "https://railway.com/dashboard",
     "icon": "◫", "category": "cloud", "open_mode": "embedded", "integration_type": "api_client",
     "repo": None},
    {"id": "bpb-worker-panel", "name": "BPB Worker Panel", "type": "panel",
     "url": None, "icon": "▤", "category": "provider", "open_mode": "embedded",
     "integration_type": "provider_adapter", "repo": "bia-pain-bache/BPB-Worker-Panel"},
    {"id": "bpb-wizard", "name": "BPB Wizard", "type": "tool",
     "url": "https://wizard.bpb-panel.workers.dev", "icon": "▥", "category": "provider",
     "open_mode": "embedded", "integration_type": "provider_adapter",
     "repo": "bia-pain-bache/BPB-Wizard"},
    {"id": "zeus", "name": "ZEUS", "type": "panel", "url": None, "icon": "▣",
     "category": "provider", "open_mode": "embedded", "integration_type": "provider_adapter",
     "repo": "panel-zeus/Z-E-U-S"},
    {"id": "rvg", "name": "RVG", "type": "provider", "url": None, "icon": "▤",
     "category": "provider", "open_mode": "embedded", "integration_type": "provider_adapter",
     "repo": None},
    {"id": "aether", "name": "Aether", "type": "runtime", "url": None, "icon": "◎",
     "category": "runtime", "open_mode": "launcher", "integration_type": "launcher",
     "repo": "MatinSenPai/Aether-GUI"},
    {"id": "nova", "name": "Nova", "type": "panel", "url": None, "icon": "▦",
     "category": "provider", "open_mode": "embedded", "integration_type": "provider_adapter",
     "repo": "IRNova/Nova-Proxy"},
    {"id": "network-checker", "name": "Network Checker", "type": "checker",
     "url": None, "icon": "⛨", "category": "tools", "open_mode": "api",
     "integration_type": "network", "repo": "mirarr-app/network-checker"},
    {"id": "xray", "name": "Xray", "type": "runtime", "url": None, "icon": "◎",
     "category": "runtime", "open_mode": "launcher", "integration_type": "runtime",
     "repo": None},
]

CATEGORY_LABELS = {"provider": "Providers", "cloud": "Cloud Services", "source": "Source Control",
                   "runtime": "Runtime", "tools": "Tools", "panels": "Panels"}


class ServiceRegistry:
    def __init__(self, store: JsonStore | None = None):
        self._store = store or JsonStore(services_path(), {"services": [], "disabled": []})

    def _read(self) -> dict:
        data = self._store.read()
        if not isinstance(data, dict):
            return {"services": [], "disabled": []}
        data.setdefault("services", [])
        data.setdefault("disabled", [])
        return data

    def presets(self) -> list[dict[str, Any]]:
        return [dict(s) for s in PRESET_SERVICES]

    def user_services(self) -> list[dict[str, Any]]:
        return [dict(s) for s in self._read()["services"]]

    def disabled_ids(self) -> list[str]:
        return list(self._read()["disabled"])

    def _write_user(self, services: list[dict], disabled: list[str]) -> None:
        self._store.write({"services": services, "disabled": disabled})

    def add(self, service: dict[str, Any]) -> dict[str, Any]:
        service = {k: v for k, v in service.items() if v is not None}
        service.setdefault("id", service.get("name", "service").lower().replace(" ", "-"))
        service.setdefault("type", "tool")
        service.setdefault("open_mode", "external")
        service.setdefault("integration_type", "manual")
        service.setdefault("enabled", True)
        data = self._read()
        data["services"] = [s for s in data["services"] if s.get("id") != service["id"]]
        data["services"].append(service)
        self._write_user(data["services"], data["disabled"])
        return service

    def remove(self, service_id: str) -> bool:
        data = self._read()
        before = len(data["services"])
        data["services"] = [s for s in data["services"] if s.get("id") != service_id]
        changed = len(data["services"]) != before
        if service_id in {s["id"] for s in PRESET_SERVICES} and service_id not in data["disabled"]:
            data["disabled"].append(service_id)
            changed = True
        self._write_user(data["services"], data["disabled"])
        return changed

    def update(self, service_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
        data = self._read()
        for s in data["services"]:
            if s.get("id") == service_id:
                for key, value in patch.items():
                    if value is not None:
                        s[key] = value
                self._write_user(data["services"], data["disabled"])
                return s
        # preset patch
        for preset in PRESET_SERVICES:
            if preset["id"] == service_id:
                updated = dict(preset)
                for key, value in patch.items():
                    if value is not None:
                        updated[key] = value
                data["services"] = [s for s in data["services"] if s.get("id") != service_id]
                data["services"].append(updated)
                self._write_user(data["services"], data["disabled"])
                return updated
        return None

    def enable(self, service_id: str) -> None:
        data = self._read()
        data["disabled"] = [d for d in data["disabled"] if d != service_id]
        self._write_user(data["services"], data["disabled"])