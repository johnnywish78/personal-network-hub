"""Credential storage with OS keyring preference and file-vault fallback.

Order of preference:
  1. OS secure credential store (`keyring`) when available.
  2. Local encrypted-file vault (0600) fallback.

Callers must never expose values; only `has()`/`keys()`/`masked()` are safe
to surface. This layer intentionally never writes secrets to git or logs.
"""

from __future__ import annotations

from typing import Optional

from .vault import SecretVault

try:  # optional dependency
    import keyring as _keyring  # type: ignore
    _KEYRING_OK = True
except Exception:  # pragma: no cover
    _KEYRING_OK = False

SERVICE_NAME = "jpnh"


class CredentialStore:
    def __init__(self, use_keyring: Optional[bool] = None):
        if use_keyring is None:
            use_keyring = _KEYRING_OK
        self._use_keyring = use_keyring and _KEYRING_OK
        self._vault = SecretVault()

    @property
    def backend(self) -> str:
        return "keyring" if self._use_keyring else "vault-file"

    def set(self, key: str, value: str) -> None:
        if self._use_keyring:
            try:
                _keyring.set_password(SERVICE_NAME, key, value)
                return
            except Exception:
                pass  # fall back to vault file
        self._vault.set(key, value)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if self._use_keyring:
            try:
                value = _keyring.get_password(SERVICE_NAME, key)
                if value is not None:
                    return value
            except Exception:
                pass
        return self._vault.get(key, default)

    def delete(self, key: str) -> None:
        if self._use_keyring:
            try:
                _keyring.delete_password(SERVICE_NAME, key)
            except Exception:
                pass
        self._vault.delete(key)

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def keys(self) -> list[str]:
        keys = set(self._vault.keys())
        if self._use_keyring:
            try:
                keys.update(_keyring.get_credential(SERVICE_NAME, None) or [])
            except Exception:
                pass
        return sorted(keys)

    def masked(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for key in self.keys():
            value = self.get(key)
            if value:
                out[key] = (value[:4] + "****" + value[-2:]) if len(value) > 8 else "****"
            else:
                out[key] = "****"
        return out