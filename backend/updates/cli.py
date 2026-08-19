"""Command-line interface for the Update Manager.

Usage (from anywhere in the checkout):

    python3 -m backend.updates.cli check
    python3 -m backend.updates.cli dry-run [project_id]
    python3 -m backend.updates.cli update <project_id> [--yes]
    python3 -m backend.updates.cli update-all [--yes]
    python3 -m backend.updates.cli rollback <backup_id>

The CLI does not require the backend server to be running. Network access
honours standard proxy environment variables (HTTP_PROXY, HTTPS_PROXY,
ALL_PROXY, NO_PROXY) so the user can activate a terminal proxy first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from .manager import UpdateManager, UpdateManagerError  # noqa: E402


def _log(level: str, _source: str, message: str) -> None:
    if level == "ERROR":
        print(f"[ERROR] {message}", file=sys.stderr)
    elif level == "WARNING":
        print(f"[WARN] {message}")
    elif level == "SUCCESS":
        print(f"[OK] {message}")
    else:
        print(f"[..] {message}")


def _print(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="jpnh-update")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="check upstream for all projects")
    p_dry = sub.add_parser("dry-run", help="plan without modifying anything")
    p_dry.add_argument("project_id", nargs="?", default=None)

    p_up = sub.add_parser("update", help="update one project")
    p_up.add_argument("project_id")
    p_up.add_argument("--yes", action="store_true",
                      help="confirm overwriting untracked/local-changed installs")

    p_all = sub.add_parser("update-all", help="update all safe projects")
    p_all.add_argument("--yes", action="store_true")

    p_rb = sub.add_parser("rollback", help="roll back to a previous backup")
    p_rb.add_argument("backup_id")

    sub.add_parser("history", help="show the update history")
    sub.add_parser("backups", help="list available backups")

    p_list = sub.add_parser("status", help="list projects and local state")
    p_list.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    manager = UpdateManager(log=_log)
    try:
        if args.command == "status":
            data = manager.status_all()
            if args.json:
                _print(data)
            else:
                for p in data["projects"]:
                    cur = p["current"].get("version") or p["current"].get("ref") or "?"
                    print(f"{p['id']:<18} {p['status']:<16} installed={cur}")
            return 0

        if args.command == "check":
            data = manager.dry_run()
            _print(_summary(data))
            return 0

        if args.command == "dry-run":
            data = manager.dry_run(args.project_id)
            _print(_summary(data))
            return 0

        if args.command == "update":
            result = manager.update(args.project_id, confirm=args.yes)
            _print(result)
            return 0 if result.get("ok") else 1

        if args.command == "update-all":
            result = manager.update_all(confirm=args.yes)
            _print(result)
            return 0

        if args.command == "rollback":
            result = manager.rollback(args.backup_id)
            _print(result)
            return 0 if result.get("ok") else 1

        if args.command == "history":
            _print({"history": manager.history.list()})
            return 0

        if args.command == "backups":
            _print({"backups": manager.backup.list()})
            return 0
    except UpdateManagerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\naborted", file=sys.stderr)
        return 130
    return 2


def _summary(data: dict) -> dict:
    if "plans" in data:
        return {
            "dry_run": True,
            "plans": [
                {
                    "project_id": p.get("project_id"),
                    "name": p.get("name"),
                    "status": p.get("status"),
                    "would_update": p.get("would_update"),
                    "current": p.get("current", {}).get("version"),
                    "available": (p.get("available") or {}).get("version"),
                    "local_changes": (p.get("local_changes") or {}).get("detected"),
                    "requires_confirmation": p.get("requires_confirmation"),
                    "build_required": p.get("build_required"),
                    "error": p.get("error"),
                }
                for p in data["plans"]
            ],
        }
    plan = data.get("plan") or data
    return {"dry_run": True, "plans": [
        {
            "project_id": plan.get("project_id"),
            "name": plan.get("name"),
            "status": plan.get("status"),
            "would_update": plan.get("would_update"),
            "current": plan.get("current", {}).get("version"),
            "available": (plan.get("available") or {}).get("version"),
            "local_changes": (plan.get("local_changes") or {}).get("detected"),
            "requires_confirmation": plan.get("requires_confirmation"),
            "build_required": plan.get("build_required"),
            "error": plan.get("error"),
        }
    ]}


if __name__ == "__main__":
    sys.exit(main())