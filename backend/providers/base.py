"""Provider adapter base class and registry.

Each external project gets a thin adapter. The Hub never reimplements an
external project's internals; adapters only expose what the project
actually supports via official APIs, GitHub metadata, or standard config
formats.
"""

from __future__ import annotations

import datetime
import json
from abc import ABC, abstractmethod
from typing import Any, Optional

from ..configs.model import NormalizedConfig


def utc_now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


class ProviderAdapter(ABC):
    """Base class for all provider adapters."""

    name: str = "provider"
    display_name: str = "Provider"
    repository_url: Optional[str] = None
    official_url: Optional[str] = None
    source_type: str = "unknown"          # github_repository | external_service | local_runtime
    integration_type: str = "unknown"     # provider_adapter | api_client | launcher
    supports: list[str] = []              # e.g. ["open", "import", "parse", "test"]

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.last_checked: Optional[str] = None

    @abstractmethod
    def describe(self) -> dict:
        """Metadata describing this provider and its capabilities."""

    def supports_action(self, action: str) -> bool:
        return action in self.supports

    def open(self) -> dict:
        return {"ok": False, "error": f"{self.name} does not support open"}

    def import_config(self, payload: str) -> list[dict]:
        return []

    def parse_config(self, payload: str) -> dict:
        return {"error": f"{self.name} has no config parser"}

    def test_config(self, cfg: NormalizedConfig) -> dict:
        return {"ok": False, "error": f"{self.name} has no config tester"}

    def _meta(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "repository_url": self.repository_url,
            "official_url": self.official_url,
            "source_type": self.source_type,
            "integration_type": self.integration_type,
            "last_checked": self.last_checked,
        }


class ProviderRegistry:
    def __init__(self):
        self._adapters: dict[str, ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> Optional[ProviderAdapter]:
        return self._adapters.get(name)

    def all(self) -> list[ProviderAdapter]:
        return list(self._adapters.values())

    def names(self) -> list[str]:
        return list(self._adapters.keys())

    def describe_all(self) -> list[dict]:
        return [adapter.describe() for adapter in self._adapters.values()]
