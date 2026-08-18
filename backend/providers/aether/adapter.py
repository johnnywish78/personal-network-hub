"""Aether integration.

Aether is an external engine. The Hub is a launcher/controller only:
detect installation, detect version, launch/stop/restart, show status,
show logs where available, and open Aether-GUI when applicable.

We never reimplement Aether internals.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import Optional

from ...providers.base import ProviderAdapter


class AetherAdapter(ProviderAdapter):
    name = "aether"
    display_name = "Aether"
    repository_url = "https://github.com/MatinSenPai/Aether-GUI"
    source_type = "local_runtime"
    integration_type = "launcher"
    supports = ["detect", "launch", "stop", "restart", "status", "logs", "open_gui"]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.binary_name = (config or {}).get("binary", "aether")

    def describe(self) -> dict:
        meta = self._meta()
        meta.update({"capabilities": self.supports, "binary": self.binary_name,
                     "detected": self.detect()["found"]})
        return meta

    def detect(self) -> dict:
        path = shutil.which(self.binary_name)
        if not path:
            return {"found": False, "path": None, "version": None, "error": "binary not found on PATH"}
        version = self._get_version(path)
        return {"found": True, "path": path, "version": version, "error": None}

    def _get_version(self, path: str) -> Optional[str]:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None

    def status(self) -> dict:
        """Check whether the Aether process is running (best effort)."""
        detected = self.detect()
        if not detected["found"]:
            return {"running": False, "detected": detected}
        try:
            result = subprocess.run(["pgrep", "-x", self.binary_name], capture_output=True, text=True, timeout=5)
            running = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            running = False
        return {"running": running, "detected": detected}

    def launch(self) -> dict:
        detected = self.detect()
        if not detected["found"]:
            return {"ok": False, "error": "Aether binary not installed"}
        try:
            subprocess.Popen([detected["path"]], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"ok": True, "action": "launch", "path": detected["path"]}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    def stop(self) -> dict:
        try:
            subprocess.run(["pkill", "-x", self.binary_name], capture_output=True, timeout=5)
            return {"ok": True, "action": "stop"}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": str(exc)}

    def restart(self) -> dict:
        self.stop()
        return self.launch()

    def logs(self) -> dict:
        return {"ok": False, "error": "Aether log access not supported on this platform"}

    def open_gui(self) -> dict:
        detected = self.detect()
        if not detected["found"]:
            return {"ok": False, "error": "Aether-GUI not detected"}
        return self.launch()
