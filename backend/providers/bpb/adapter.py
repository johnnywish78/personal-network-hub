"""BPB integration.

Two components:
  * BPB Worker Panel  - deployed Cloudflare worker panel (open, store URL,
                        import/parse generated configs, test, save)
  * BPB Wizard        - deployment helper (open wizard, open deployed panel)

The Hub does not duplicate the BPB panel UI; it manages access and workflow.
"""

from __future__ import annotations

from typing import Optional

from ...configs import parser as config_parser
from ...providers.base import ProviderAdapter


class BPBWorkerPanelAdapter(ProviderAdapter):
    name = "bpb-worker-panel"
    display_name = "BPB Worker Panel"
    repository_url = "https://github.com/bia-pain-bache/BPB-Worker-Panel"
    source_type = "github_repository"
    integration_type = "provider_adapter"
    supports = ["open", "configure", "import", "parse", "test", "copy", "export"]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.panel_url = (config or {}).get("panel_url")

    def describe(self) -> dict:
        meta = self._meta()
        meta.update({
            "panel_url": self.panel_url,
            "capabilities": self.supports,
        })
        return meta

    def open(self) -> dict:
        if not self.panel_url:
            return {"ok": False, "error": "no BPB panel URL stored; configure it first"}
        return {"ok": True, "url": self.panel_url, "action": "open"}

    def set_panel_url(self, url: str) -> dict:
        self.panel_url = url
        self.config["panel_url"] = url
        return {"ok": True, "panel_url": url}

    def import_config(self, payload: str) -> list[dict]:
        """Import generated configs (share links) produced by the panel."""
        parsed = config_parser.parse_many(payload)
        return parsed

    def parse_config(self, payload: str) -> dict:
        result = config_parser.parse_many(payload)
        return {"ok": True, "parsed": result}


class BPBWizardAdapter(ProviderAdapter):
    name = "bpb-wizard"
    display_name = "BPB Wizard"
    repository_url = "https://github.com/bia-pain-bache/BPB-Wizard"
    official_url = "https://bpb-wizard.bia-pain-bache.pages.dev"
    source_type = "github_repository"
    integration_type = "provider_adapter"
    supports = ["open", "deploy_helper", "open_panel"]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)

    def describe(self) -> dict:
        meta = self._meta()
        meta["capabilities"] = self.supports
        return meta

    def open(self) -> dict:
        return {"ok": True, "url": self.official_url, "action": "open_wizard"}
