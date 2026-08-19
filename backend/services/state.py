"""Application state container shared across API routes.

Centralizes singletons: config store, settings, vault, logs, history,
clients, provider registry, and external API clients.
"""

from __future__ import annotations

from ..configs.storage import ConfigStore
from ..providers.cloudflare.client import CloudflareClient
from ..providers.github.client import GitHubClient
from ..providers.railway.client import RailwayClient
from ..services.client_detector import detect_clients
from ..services.history import TestHistory
from ..services.logging import LogHub
from ..services.registry import ServiceRegistry
from ..services.settings import Settings
from ..storage.credential_store import CredentialStore
from ..xray.manager import XrayManager
from ..providers.registry import build_registry
from ..updates.history import UpdateHistory
from ..updates.manager import UpdateManager
from .network_checker import network_checker_manager


class AppState:
    def __init__(self):
        self.settings = Settings()
        self.vault = CredentialStore()
        self.logs = LogHub()
        self.history = TestHistory()
        self.config_store = ConfigStore()
        self.providers = build_registry()
        self.services = ServiceRegistry()
        self.xray = XrayManager()
        self.cloudflare = CloudflareClient(token_provider=lambda: self.vault.get("cloudflare_token"))
        self.railway = RailwayClient(token_provider=lambda: self.vault.get("railway_token"))
        self.github = GitHubClient(token_provider=lambda: self.vault.get("github_token"))
        self.update_history = UpdateHistory()
        self.updates = UpdateManager(
            log=lambda level, source, message: self.logs.log(level, source, message))

    def client_status(self) -> list[dict]:
        return detect_clients(self.settings.get("client_paths"))

    # --- Service registry helpers -----------------------------------------

    def service_url(self, service_id: str) -> str | None:
        """Resolve the best URL for a service (user override > settings > preset)."""
        for user in self.services.user_services():
            if user.get("id") == service_id and user.get("url"):
                return user["url"]
        preset = next((s for s in self.services.presets() if s["id"] == service_id), None)
        stored = self.settings.get(f"provider_urls.{service_id}")
        if stored:
            return stored
        return (preset or {}).get("url")

    def service_status(self, service_id: str) -> dict:
        """Live status for one service (does not block on network)."""
        url = self.service_url(service_id)
        if service_id in ("github",):
            return self.github.check()
        if service_id == "cloudflare":
            return self.cloudflare.check()
        if service_id == "railway":
            return self.railway.check()
        if service_id == "xray":
            s = self.xray.status()
            return {"status": "ok" if s["installed"] else "not-installed",
                    "detail": s["version"] or s["path"], "error": None}
        if service_id == "aether":
            adapter = self.providers.get("aether")
            found = adapter.detect()["found"] if adapter else False
            return {"status": "ok" if found else "not-installed", "detail": None, "error": None}
        if service_id == "network-checker":
            found = network_checker_manager().bundle_detected()
            return {"status": "ok" if found else "not-installed",
                    "detail": None if found else "bundle not present", "error": None}
        if url:
            return {"status": "configured", "detail": url, "error": None}
        return {"status": "not-configured", "detail": None, "error": None}

    def service_list(self) -> list[dict]:
        """Merged list of enabled preset + user services with live status."""
        disabled = set(self.services.disabled_ids())
        user_ids = {s["id"] for s in self.services.user_services()}
        result = []
        for service in self.services.presets():
            if service["id"] in disabled:
                continue
            entry = dict(service)
            entry["url"] = self.service_url(service["id"])
            entry["status"] = self.service_status(service["id"])
            result.append(entry)
        for service in self.services.user_services():
            if service["id"] in user_ids and service["id"] not in {s["id"] for s in self.services.presets()}:
                entry = dict(service)
                entry["url"] = service.get("url")
                entry["user"] = True
                entry["status"] = self.service_status(service["id"])
                result.append(entry)
        return result

    def open_service(self, service_id: str) -> dict:
        """Resolve the open action for a service."""
        service = next((s for s in self.service_list() if s["id"] == service_id), None)
        if not service:
            return {"ok": False, "error": "unknown service"}
        url = service.get("url")
        mode = service.get("open_mode", "external")
        if service_id == "xray":
            return {"ok": True, "mode": "xray", "url": None, "action": "open_xray"}
        if service_id == "aether":
            adapter = self.providers.get("aether")
            if not adapter or not adapter.detect()["found"]:
                return {"ok": False, "mode": mode, "url": url, "error": "Aether not installed"}
            return {"ok": True, "mode": "launcher", "url": None, "action": "launch"}
        if service_id == "network-checker":
            found = network_checker_manager().bundle_detected()
            if not found:
                return {"ok": False, "mode": mode, "url": None,
                        "error": "Network Checker bundle not present"}
            return {"ok": True, "mode": "launcher", "url": None,
                    "action": "launch", "app": "network-checker"}
        if not url:
            return {"ok": False, "mode": mode, "url": None,
                    "error": f"{service.get('name')} has no URL configured"}
        return {"ok": True, "mode": mode, "url": url, "action": "open"}

    def provider_status(self) -> dict:
        out = {}
        for name, provider in {
            "bpb-worker-panel": "bpb-worker-panel",
            "zeus": "zeus",
            "rvg": "rvg",
            "aether": "aether",
            "nova": "nova",
        }.items():
            adapter = self.providers.get(provider)
            if adapter is None:
                continue
            describe = adapter.describe()
            status = "unknown"
            if adapter.name == "aether":
                status = "detected" if describe.get("detected") else "not-installed"
            elif describe.get("panel_url"):
                status = "configured"
            else:
                status = "not-configured"
            out[name] = {"status": status, **describe}
        return out


app_state = AppState()
