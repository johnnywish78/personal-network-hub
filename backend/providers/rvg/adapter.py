"""RVG adapter.

RVG is a provider focused on VLESS configurations (VLESS + TLS + XHTTP).
Supports storing panel URL, importing/parsing VLESS URIs into normalized
internal data, saving, testing, copying, exporting, and QR generation.
"""

from __future__ import annotations

import base64
import io
from typing import Optional

import qrcode

from ...configs import parser as config_parser
from ...configs.model import NormalizedConfig
from ...configs.normalizer import normalize
from ...providers.base import ProviderAdapter


class RvgAdapter(ProviderAdapter):
    name = "rvg"
    display_name = "RVG"
    source_type = "provider"
    integration_type = "provider_adapter"
    supports = ["open", "configure", "import", "parse", "save", "test", "copy", "export", "qr"]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.panel_url = (config or {}).get("panel_url")

    def describe(self) -> dict:
        meta = self._meta()
        meta.update({"panel_url": self.panel_url, "capabilities": self.supports})
        return meta

    def open(self) -> dict:
        if not self.panel_url:
            return {"ok": False, "error": "no RVG panel URL stored"}
        return {"ok": True, "url": self.panel_url, "action": "open"}

    def set_panel_url(self, url: str) -> dict:
        self.panel_url = url
        self.config["panel_url"] = url
        return {"ok": True, "panel_url": url}

    def import_config(self, payload: str) -> list[dict]:
        """Import VLESS URIs (possibly many, possibly subscription output)."""
        return config_parser.parse_many(payload)

    def parse_config(self, payload: str) -> dict:
        """Parse a VLESS URI into normalized internal data."""
        single = config_parser.parse_single(payload)
        if single is None:
            return {"ok": False, "error": "unparseable payload"}
        if "error" in single:
            return {"ok": False, "error": single["error"]}
        cfg = normalize(single, provider="RVG")
        return {"ok": True, "config": cfg.to_public_dict(), "parameters": {
            "protocol": cfg.protocol, "address": cfg.address, "port": cfg.port,
            "uuid": cfg.uuid, "security": cfg.security, "sni": cfg.sni,
            "fingerprint": cfg.fingerprint, "alpn": cfg.alpn, "network": cfg.network,
            "host": cfg.host, "path": cfg.path, "mode": cfg.mode,
            "flow": cfg.flow,
        }}

    def to_qr_base64(self, uri: str) -> str:
        """Generate a QR code for a URI, returning base64 PNG data."""
        qr = qrcode.QRCode(version=None, box_size=10, border=2)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def copy_uri(self, cfg: NormalizedConfig) -> dict:
        uri = cfg.raw_config or f"vless://{cfg.uuid}@{cfg.address}:{cfg.port}"
        return {"ok": True, "uri": uri}
