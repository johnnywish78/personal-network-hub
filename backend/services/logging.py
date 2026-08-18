"""Unified log viewer.

Log levels: INFO, SUCCESS, WARNING, ERROR.
Security rule: never log tokens, passwords, private keys, or full
credentials. The `redact` helper strips URI credentials before logging.
"""

from __future__ import annotations

import datetime
import re
import threading
from typing import Optional

from ..storage.json_store import JsonStore
from ..storage.paths import log_entries_path

MAX_ENTRIES = 500


def redact(text: str) -> str:
    """Redact credentials from share-link style strings before logging."""
    if not text:
        return text
    # vless://uuid@host -> vless://REDACTED@host
    text = re.sub(r"(vless|vmess|trojan|ss|hysteria2|hy2)://[^@\s]+@",
                  r"\1://REDACTED@", text)
    # query parameters that carry secrets
    for param in ("password", "privatekey", "obfs-password"):
        text = re.sub(rf"({param}=)[^&\s]+", r"\1REDACTED", text, flags=re.IGNORECASE)
    return text


class LogHub:
    def __init__(self, store: JsonStore | None = None):
        self._store = store or JsonStore(log_entries_path(), [])
        self._lock = threading.RLock()

    def log(self, level: str, source: str, message: str) -> dict:
        level = level.upper()
        if level not in ("INFO", "SUCCESS", "WARNING", "ERROR"):
            level = "INFO"
        entry = {
            "level": level,
            "source": source,
            "message": redact(str(message)),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        }
        with self._lock:
            entries = self._store.read()
            if not isinstance(entries, list):
                entries = []
            entries.append(entry)
            if len(entries) > MAX_ENTRIES:
                entries = entries[-MAX_ENTRIES:]
            self._store.write(entries)
        return entry

    def info(self, source: str, message: str): return self.log("INFO", source, message)
    def success(self, source: str, message: str): return self.log("SUCCESS", source, message)
    def warning(self, source: str, message: str): return self.log("WARNING", source, message)
    def error(self, source: str, message: str): return self.log("ERROR", source, message)

    def entries(self, level: Optional[str] = None) -> list[dict]:
        with self._lock:
            entries = self._store.read()
            if not isinstance(entries, list):
                return []
            if level:
                entries = [e for e in entries if e.get("level") == level.upper()]
            return list(reversed(entries))

    def clear(self) -> None:
        with self._lock:
            self._store.write([])

    def export(self) -> str:
        lines = []
        for e in reversed(self.entries()):
            lines.append(f"[{e['timestamp']}] {e['level']:<7} {e['source']}: {e['message']}")
        return "\n".join(lines)
