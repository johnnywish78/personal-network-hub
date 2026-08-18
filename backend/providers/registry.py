"""Application provider registry singleton wiring all adapters."""

from __future__ import annotations

from .base import ProviderRegistry
from .bpb.adapter import BPBWizardAdapter, BPBWorkerPanelAdapter
from .nova.adapter import NovaAdapter
from .rvg.adapter import RvgAdapter
from .zeus.adapter import ZeusAdapter
from .aether.adapter import AetherAdapter


def build_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(BPBWorkerPanelAdapter())
    registry.register(BPBWizardAdapter())
    registry.register(ZeusAdapter())
    registry.register(RvgAdapter())
    registry.register(AetherAdapter())
    registry.register(NovaAdapter())
    return registry
