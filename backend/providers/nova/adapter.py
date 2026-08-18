"""Nova adapter.

Capabilities limited to what the Nova repository reliably exposes:
open project/panel, import config, parse, save, test, export.
No unsupported functionality is invented.
"""

from __future__ import annotations

from typing import Optional

from ...configs import parser as config_parser
from ...providers.base import ProviderAdapter


class NovaAdapter(ProviderAdapter):
    name = "nova"
    display_name = "Nova"
    repository_url = "https://github.com/IRNova/Nova-Proxy"
    source_type = "github_repository"
    integration_type = "provider_adapter"
    supports = ["open", "import", "parse", "save", "test", "export"]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.panel_url = (config or {}).get("panel_url")

    def describe(self) -> dict:
        meta = self._meta()
        meta.update({"panel_url": self.panel_url, "capabilities": self.supports})
        return meta

    def open(self) -> dict:
        if not self.panel_url:
            return {"ok": False, "error": "no Nova panel URL stored"}
        return {"ok": True, "url": self.panel_url, "action": "open"}

    def set_panel_url(self, url: str) -> dict:
        self.panel_url = url
        self.config["panel_url"] = url
        return {"ok": True, "panel_url": url}

    def import_config(self, payload: str) -> list[dict]:
        return config_parser.parse_many(payload)

    def parse_config(self, payload: str) -> dict:
        return {"ok": True, "parsed": config_parser.parse_many(payload)}
