"""CLI entry point for applying a pending JPNH self-update on restart.

Invoked by the desktop host (``desktop/lib/self-updater.js``) at application
startup, before the backend begins serving:

    .venv/bin/python -m backend.updates.apply_pending

Reads ``~/.jpnh/pending-apply.json``, validates + applies the staged JPNH Core
source, and exits 0 on success / 1 on failure. Never touches the network.
"""

from __future__ import annotations

import sys

from ..storage.paths import pending_apply_path
from .manager import UpdateManager
from .self_update import apply_staged_source, pending_apply_info


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if "--clear" in argv:
            pending_apply_path().unlink(missing_ok=True)
            print("pending apply marker cleared")
            return 0

        marker = pending_apply_info()
        if not marker:
            print("no pending self-update")
            return 0

        manager = UpdateManager()
        result = apply_staged_source(manager, marker)
        if not result.get("ok"):
            print(f"self-update failed: {result.get('error')}", file=sys.stderr)
            return 1
        print(f"self-update applied: {result.get('new_version')}")
        return 0
    except Exception as exc:  # pragma: no cover - defensive
        print(f"self-update error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
