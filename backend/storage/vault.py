"""Secure local secret vault.

Secrets (Cloudflare token, Railway token, GitHub token, panel passwords) are
stored in a single JSON file with restrictive file permissions (0600) and
loaded into memory only when needed.

Security rules enforced by the rest of the app:
  * Secrets are never exposed through API responses.
  * Secrets are never printed to logs.
  * Secrets are never written to git (vault file is gitignored).
"""

from __future__ import annotations

import json
import os
import stat
from typing import Any

from .paths import secrets_path


class SecretVault:
    def __init__(self, path=None):
        self._path = path or secrets_path()
        self._ensure_permissions()

    def _ensure_permissions(self) -> None:
        if self._path.exists():
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        self._ensure_permissions()
        self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)

    # --- CRUD ---------------------------------------------------------

    def set(self, key: str, value: str) -> None:
        data = self._read()
        data[key] = value
        self._write(data)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._read().get(key, default)

    def delete(self, key: str) -> None:
        data = self._read()
        data.pop(key, None)
        self._write(data)

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def keys(self) -> list[str]:
        """Return secret keys WITHOUT their values (safe to expose)."""
        return list(self._read().keys())

    def masked(self) -> dict[str, str]:
        """Return a mapping of key -> masked preview for UI display."""
        out: dict[str, str] = {}
        for key, value in self._read().items():
            if isinstance(value, str) and value:
                out[key] = value[:4] + "****" + value[-2:] if len(value) > 8 else "****"
            else:
                out[key] = "****"
        return out
