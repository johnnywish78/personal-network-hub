"""Safe version and reference comparison for the Update Manager.

Versions may come from GitHub tags (``v1.2.3``, ``1.2.3``, ``jpnh-0.1.0``),
pubspec files (``1.5.0``), or the JPNH ``VERSION`` file. Comparing them must
never raise on odd input; an unparseable version compares as ``None`` so the
caller can fall back to a conservative ``unknown`` status instead of a crash.
"""

from __future__ import annotations

import re
from typing import Optional

_TAG_VERSION = re.compile(r"[^\d]*(\d+(?:\.\d+)*)")


class Version:
    """A simple numeric dotted version that compares safely."""

    __slots__ = ("raw", "parts")

    def __init__(self, raw: str):
        self.raw = str(raw).strip()
        self.parts = _parse_parts(self.raw)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self.parts == other.parts

    def __lt__(self, other: "Version") -> bool:
        if self.parts is None or other.parts is None:
            return False
        return self.parts < other.parts

    def __le__(self, other: "Version") -> bool:
        return self == other or self < other

    def __gt__(self, other: "Version") -> bool:
        if self.parts is None or other.parts is None:
            return False
        return self.parts > other.parts

    def __ge__(self, other: "Version") -> bool:
        return self == other or self > other

    def __bool__(self) -> bool:
        return self.parts is not None

    def __repr__(self) -> str:
        return f"Version({self.raw!r})"


def _parse_parts(raw: str) -> Optional[tuple[int, ...]]:
    """Extract a dotted numeric tuple from arbitrary version-ish text."""
    if not raw:
        return None
    match = _TAG_VERSION.search(raw)
    if not match:
        return None
    try:
        return tuple(int(p) for p in match.group(1).split("."))
    except (TypeError, ValueError):
        return None


def compare_versions(a: Optional[str], b: Optional[str]) -> Optional[int]:
    """Return -1 (a < b), 0 (equal), 1 (a > b), or None if incomparable."""
    if a is None or b is None:
        return None
    va = Version(a)
    vb = Version(b)
    if not va or not vb:
        return None
    if va == vb:
        return 0
    return -1 if va < vb else 1


def strip_tag(tag: str) -> str:
    """Normalize a git tag into a comparable version string."""
    tag = tag.strip()
    match = _TAG_VERSION.search(tag)
    return match.group(1) if match else tag


def short_sha(sha: Optional[str], length: int = 8) -> str:
    """Short, safe display form of a commit sha."""
    if not sha:
        return "unknown"
    sha = str(sha).strip()
    return sha[:length] if len(sha) > length else sha


def is_valid_sha(value: Optional[str]) -> bool:
    return bool(value) and bool(re.fullmatch(r"[0-9a-fA-F]{7,64}", str(value)))