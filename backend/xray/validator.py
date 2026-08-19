"""Xray config validation (`xray run -test`)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional


def validate_config(binary: Optional[str], config_path: str) -> dict:
    """Validate an Xray JSON config using `xray run -test`."""
    if not binary:
        return {"valid": False, "error": "xray not installed"}
    path = Path(config_path).expanduser()
    if not path.exists():
        return {"valid": False, "error": f"config file not found: {path}"}
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"valid": False, "error": f"invalid JSON: {exc}"}
    try:
        result = subprocess.run([binary, "run", "-test", "-c", str(path)],
                                capture_output=True, text=True, timeout=15)
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            return {"valid": True, "output": "OK" if not output else output[-500:]}
        return {"valid": False, "output": output[-500:] or "failed"}
    except subprocess.TimeoutExpired:
        return {"valid": False, "error": "validation timed out"}
    except OSError as exc:
        return {"valid": False, "error": str(exc)}
