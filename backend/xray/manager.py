"""Xray manager: start/stop/restart and status.

Xray is fully optional: if it is not installed the rest of the application
keeps working. All Xray interactions use safe subprocess execution with
timeouts.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from .detector import find_binary, is_running, version_of
from .validator import validate_config


class XrayManager:
    def __init__(self, binary: Optional[str] = None):
        self.binary = find_binary(binary) if binary else find_binary()

    def detect(self) -> dict:
        if not self.binary:
            return {"installed": False, "version": None, "path": None, "running": False, "error": None}
        return {
            "installed": True,
            "version": version_of(self.binary),
            "path": self.binary,
            "running": is_running(self.binary),
            "error": None,
        }

    def status(self) -> dict:
        detected = self.detect()
        return {"installed": detected["installed"], "version": detected["version"],
                "path": detected["path"], "running": detected["running"]}

    def start(self, config_path: Optional[str] = None) -> dict:
        if not self.binary:
            return {"ok": False, "error": "xray not installed"}
        if is_running(self.binary):
            return {"ok": True, "already_running": True}
        cmd = [self.binary, "run"]
        if config_path:
            cmd += ["-c", config_path]
        try:
            log_file = Path(config_path).expanduser().with_name("xray-stderr.log") if config_path \
                else Path.home() / ".jpnh" / "xray-stderr.log"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, "a") as errlog:
                subprocess.Popen(cmd, start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=errlog)
            return {"ok": True, "action": "start"}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

    def stop(self) -> dict:
        if not self.binary:
            return {"ok": False, "error": "xray not installed"}
        name = Path(self.binary).name
        try:
            subprocess.run(["pkill", "-f", name], capture_output=True, timeout=5)
            return {"ok": True, "action": "stop"}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": str(exc)}

    def restart(self, config_path: Optional[str] = None) -> dict:
        self.stop()
        return self.start(config_path)

    def validate_config(self, config_path: str) -> dict:
        return validate_config(self.binary, config_path)
