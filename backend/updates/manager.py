"""Update Manager — orchestrates checking, updating, backing up, building,
health-checking, and rolling back managed projects/components.

The manager is generic: it works off :class:`ProjectManifest` definitions and
:class:`UpdateSource` strategies. New components are added through the
registry (a manifest) and, only when they use a brand-new mechanism, a new
source strategy — never by rewriting the manager.

Safety rules enforced here:

* never modify a project whose source is ``none``/``local``
* never swap the running JPNH checkout in place (``staging_only``)
* detect local modifications and require explicit confirmation
* skip unsafe projects during Update All and report them
* every update is preceded by a recoverable backup
* health-check after apply; auto-rollback on failure
* never log or store credentials
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from ..storage.paths import update_cache_dir
from .backup import BackupManager
from .health import HealthCheckManager, current_jpnh_version
from .history import UpdateHistory
from .manifest import ProjectManifest
from .registry import ProjectRegistry
from .sources import (GitHubSource, LocalSource, UpdateSource,
                      UpdateSourceError, file_hashes, parse_version_from_file,
                      tree_fingerprint)
from .state import UpdateState
from .versions import compare_versions

METADATA_FILE = ".jpnh-update.json"

VALID_STATUS = {"up-to-date", "update-available", "installed", "missing",
                "unknown", "disabled", "error", "newer-than-remote",
                "no-stable-release"}


class UpdateManagerError(Exception):
    pass


class UpdateManager:
    def __init__(self, registry: Optional[ProjectRegistry] = None,
                 state: Optional[UpdateState] = None,
                 history: Optional[UpdateHistory] = None,
                 backup: Optional[BackupManager] = None,
                 health: Optional[HealthCheckManager] = None,
                 root: Optional[Path] = None,
                 log: Optional[Callable[[str, str, str], None]] = None):
        self.registry = registry or ProjectRegistry()
        self.state = state or UpdateState()
        self.history = history or UpdateHistory()
        self.backup = backup or BackupManager(root=root)
        self.health = health or HealthCheckManager(root=root)
        self.root = root or Path(__file__).resolve().parents[2]
        self._log = log or (lambda _level, _src, _msg: None)

    # -- helpers ---------------------------------------------------------------

    def _log_info(self, msg: str): self._log("INFO", "updates", msg)
    def _log_ok(self, msg: str): self._log("SUCCESS", "updates", msg)
    def _log_warn(self, msg: str): self._log("WARNING", "updates", msg)
    def _log_err(self, msg: str): self._log("ERROR", "updates", msg)

    def source_for(self, manifest: ProjectManifest) -> UpdateSource:
        if manifest.source_type in ("github", "git"):
            return GitHubSource()
        if manifest.source_type in ("local", "none"):
            return LocalSource()
        raise UpdateManagerError(f"no source implementation for '{manifest.source_type}'")

    def _read_metadata(self, project: ProjectManifest) -> Optional[dict]:
        """Installed-update metadata from the project dir, then state fallback."""
        install_dir = project.install_dir(self.root)
        meta_path = install_dir / METADATA_FILE
        if meta_path.exists():
            try:
                return json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
        stored = self.state.get(project.id)
        if stored.get("installed_ref") or stored.get("adopted") or stored.get("installed_fingerprint"):
            return stored
        return None

    def _write_metadata(self, project: ProjectManifest, data: dict) -> None:
        install_dir = project.install_dir(self.root)
        meta_path = install_dir / METADATA_FILE
        try:
            meta_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass  # non-fatal; state still records it
        self.state.set(project.id, **data)

    # -- current state -----------------------------------------------------------

    def current_version(self, project: ProjectManifest,
                        meta: Optional[dict] = None) -> dict[str, Any]:
        """Detect the locally installed version/reference for a project."""
        install_dir = project.install_dir(self.root)
        version = None
        ref = None
        ref_type = None
        # A staging-only project (JPNH core) is never swapped in place, so it
        # is always considered a known, tracked install.
        tracked = bool(project.staging_only)

        if meta is None:
            meta = self._read_metadata(project)
        if meta:
            ref = meta.get("ref")
            ref_type = meta.get("ref_type")
            tracked = True
            version = meta.get("version") or meta.get("installed_version")

        if version is None:
            if project.current_version_file:
                version = parse_version_from_file(install_dir / project.current_version_file)
            if version is None and project.version_detection == "release":
                version = ref
            if version is None and project.version_detection == "commit":
                version = (ref or "")[:8] or None

        return {
            "version": version,
            "ref": ref,
            "ref_type": ref_type,
            "tracked": tracked,
            "installed": install_dir.exists(),
            "install_path": str(install_dir),
        }

    def local_changes(self, project: ProjectManifest,
                      meta: Optional[dict] = None) -> dict[str, Any]:
        """Detect local modifications versus the last installed state."""
        if project.staging_only or not project.install_path or project.install_path == ".":
            return {"detected": False, "tracked": True, "files": []}
        install_dir = project.install_dir(self.root)
        if meta is None:
            meta = self._read_metadata(project)
        recorded_fp = (meta or {}).get("installed_fingerprint")
        if not recorded_fp:
            return {"detected": None, "tracked": False, "files": [],
                    "reason": "installation is not tracked by the update manager"}
        current_fp = tree_fingerprint(install_dir, project)
        if current_fp == recorded_fp:
            return {"detected": False, "tracked": True, "files": []}
        # precise diff
        recorded_hashes = (meta or {}).get("installed_hashes") or {}
        current_hashes = file_hashes(install_dir, project)
        changed = [p for p, h in current_hashes.items() if recorded_hashes.get(p) != h]
        added = [p for p in current_hashes if p not in recorded_hashes]
        removed = [p for p in recorded_hashes if p not in current_hashes]
        files = sorted(set(changed + added + removed))[:50]
        return {"detected": True, "tracked": True, "files": files}

    # -- adoption / baselining -----------------------------------------------------

    def _virtual_adoption(self, project: ProjectManifest) -> Optional[dict]:
        """Compute the baseline metadata a real adoption would record, without
        writing anything. Returns None when the component cannot be baselined.
        """
        if project.staging_only:
            return None
        if not project.enabled:
            return None
        if project.source_type not in ("github", "git"):
            return None
        if not project.install_path or project.install_path == ".":
            return None
        if self._read_metadata(project):
            return None  # already tracked
        install_dir = project.install_dir(self.root)
        if not install_dir.exists():
            return None
        for rel in project.required_files or []:
            if not (install_dir / rel).exists():
                return None
        version = None
        if project.current_version_file:
            version = parse_version_from_file(install_dir / project.current_version_file)
        if version is None:
            return None  # no baseline derivable -> leave untouched
        return {
            "source_type": project.source_type,
            "repository": project.repository,
            "ref": None,
            "ref_type": None,
            "version": version,
            "installed_version": version,
            "installed_fingerprint": tree_fingerprint(install_dir, project),
            "installed_hashes": file_hashes(install_dir, project),
            "adopted": True,
        }

    def _adopt_if_unmanaged(self, project: ProjectManifest) -> bool:
        """Baseline an existing, unmanaged installation without downloading.

        When a vendored component is already present (Network Checker), has its
        required files, and exposes a detectable version, the Update Manager
        adopts it as a tracked install: fingerprints + hashes are recorded from
        the existing files so local-change detection keeps working, but nothing
        is downloaded, overwritten, or modified. Returns True if a new baseline
        was established.
        """
        baseline = self._virtual_adoption(project)
        if not baseline:
            return False
        self._log_info(
            f"adopting existing {project.id} as a tracked install "
            f"(version {baseline['version']}) from {project.install_dir(self.root)}")
        self._write_metadata(project, baseline)
        return True

    # -- status -------------------------------------------------------------------

    def status_entry(self, project: ProjectManifest) -> dict[str, Any]:
        base = project.to_dict()
        self._adopt_if_unmanaged(project)
        current = self.current_version(project)
        local = self.local_changes(project)
        stored = self.state.get(project.id)
        status = "unknown"
        error = None

        if not project.enabled:
            status = "disabled"
        elif project.source_type in ("none", "local"):
            status = "up-to-date" if current.get("installed") else "unknown"
        else:
            # offline: use the last cached upstream result when available
            cached_ref = stored.get("available_ref")
            if cached_ref:
                cached_available = {
                    "ref": cached_ref,
                    "ref_type": "commit",
                    "version": stored.get("available_version"),
                    "release_tag": stored.get("available_release_tag"),
                    "published_at": None,
                    "url": f"https://github.com/{project.repository}",
                    "development": bool(stored.get("development")),
                }
                status, _ = self._status_from(project, current, cached_available)
                error = stored.get("last_error")
            elif current.get("tracked"):
                status = "unknown"  # installed and managed, never checked upstream
            elif current.get("installed"):
                status = "installed"  # present, no baseline yet
            else:
                status = "missing"

        try:
            health = self.health.run(project, backend_alive=True)
        except Exception as exc:  # a failing health probe must not break status
            health = {"ok": False, "checks": [], "error": str(exc)}

        backups = self.backup.list(project=project.id)

        entry = {
            **base,
            "current": current,
            "local_changes": local,
            "status": status,
            "available": None,
            "note": None,
            "last_update": stored.get("updated_at"),
            "last_check": stored.get("last_check"),
            "error": error,
            "staged_ref": stored.get("staged_ref"),
            "health": {
                "ok": bool(health.get("ok")),
                "checks": health.get("checks", []),
                "error": health.get("error"),
            },
            "build": {
                "required": project.build_strategy not in ("none",) or bool(project.build_command),
                "last": stored.get("build_status"),
                "detail": stored.get("build_detail"),
            },
            "backup_available": len(backups),
            "rollback_available": len(backups),
            "adopted": bool(stored.get("adopted")),
        }
        return entry

    def status_all(self, *, check: bool = False) -> dict[str, Any]:
        """Combined status for all projects.

        ``check=True`` performs a live upstream check per project (may hit the
        network); ``check=False`` only uses cached/local state.
        """
        entries = [self.status_entry(m) for m in self.registry.list()]
        if check:
            for entry in entries:
                if entry["status"] in ("disabled", "up-to-date"):
                    continue
                try:
                    plan = self.check(entry["id"])
                    entry["status"] = plan["status"]
                    entry["available"] = plan["available"]
                    entry["error"] = plan["error"]
                except UpdateManagerError as exc:
                    entry["status"] = "error"
                    entry["error"] = str(exc)
        return {"projects": entries, "errors": self.registry.errors()}

    # -- check / dry-run ------------------------------------------------------------

    def check(self, project_id: str) -> dict[str, Any]:
        """Query upstream and produce a plan. No files are modified."""
        project = self._require(project_id)
        return self._build_plan(project, dry_run=True)

    def dry_run(self, project_id: Optional[str] = None) -> dict[str, Any]:
        """Check-only mode for one project or all; never modifies anything."""
        if project_id:
            return {"dry_run": True, "plan": self.check(project_id)}
        plans = []
        for project in self.registry.list():
            try:
                plans.append(self._build_plan(project, dry_run=True))
            except UpdateManagerError as exc:
                plans.append(self._error_plan(project, str(exc)))
        return {"dry_run": True, "plans": plans}

    def _build_plan(self, project: ProjectManifest, dry_run: bool = True) -> dict[str, Any]:
        if not project.enabled:
            raise UpdateManagerError(f"project '{project.id}' is disabled")
        if project.source_type in ("none", "local"):
            current = self.current_version(project)
            return {
                "project_id": project.id,
                "name": project.name,
                "current": current,
                "available": None,
                "status": "up-to-date" if current.get("installed") else "unknown",
                "would_update": False,
                "development": False,
                "note": None,
                "build_required": False,
                "requires_confirmation": False,
                "local_changes": self.local_changes(project),
                "error": None,
            }

        source = self.source_for(project)
        self._log_info(f"checking {project.id} against {project.repository}")
        try:
            available = source.check_available(project)
        except UpdateSourceError as exc:
            self.state.set(project.id, last_check=_now_iso(), last_error=str(exc))
            self._log_warn(f"check failed for {project.id}: {exc}")
            return self._error_plan(project, str(exc))

        current = None
        local = None
        if dry_run:
            # A check must never modify anything: adopt virtually only.
            virtual = self._virtual_adoption(project)
            current = self.current_version(project, meta=virtual)
            local = self.local_changes(project, meta=virtual)
        else:
            self._adopt_if_unmanaged(project)
            current = self.current_version(project)
            local = self.local_changes(project)
        status, would_update = self._status_from(project, current, available)
        development = bool(available.get("development"))
        requires_confirmation = bool(local.get("detected") or not local.get("tracked"))
        if development and project.release_only:
            # stable-only project: a branch-head build is never applied silently
            requires_confirmation = True
        plan = {
            "project_id": project.id,
            "name": project.name,
            "current": current,
            "available": available,
            "status": status,
            "would_update": would_update,
            "development": development,
            "note": available.get("note"),
            "build_required": project.build_strategy not in ("none",) or bool(project.build_command),
            "requires_confirmation": requires_confirmation,
            "local_changes": local,
            "staging_only": project.staging_only,
            "dry_run": dry_run,
            "error": None,
        }
        self.state.set(project.id, last_check=_now_iso(),
                       last_error=None,
                       available_ref=available.get("ref"),
                       available_version=available.get("version"),
                       available_release_tag=available.get("release_tag"),
                       development=bool(available.get("development")),
                       available_status=status)
        return plan

    def _status_from(self, project: ProjectManifest, current: dict, available: dict) -> tuple[str, bool]:
        # A stable-only project must never present a branch-head development
        # build as a stable update.
        if available.get("development") and project.release_only:
            return "no-stable-release", False
        cur_ref = current.get("ref")
        new_ref = available.get("ref")
        if cur_ref and new_ref and cur_ref == new_ref:
            return "up-to-date", False
        cur_ver = current.get("version")
        new_ver = available.get("version")
        cmp = compare_versions(cur_ver, new_ver) if (cur_ver and new_ver) else None
        if cmp == 1:
            return "newer-than-remote", False
        if not current.get("installed"):
            return "missing", bool(new_ref)
        if not current.get("tracked"):
            # present but the update manager has no baseline for it yet; the
            # first update backs it up and establishes one
            return "installed", bool(new_ref)
        if cmp == 0:
            if cur_ref and new_ref:
                return "up-to-date" if cur_ref == new_ref else "update-available", True
            return "update-available" if new_ref else "up-to-date", bool(new_ref)
        if cmp is None:
            return "unknown" if not new_ref else "update-available", bool(new_ref)
        return "update-available", True

    def _error_plan(self, project: ProjectManifest, error: str) -> dict[str, Any]:
        return {
            "project_id": project.id,
            "name": project.name,
            "current": self.current_version(project),
            "available": None,
            "status": "error",
            "would_update": False,
            "development": False,
            "note": None,
            "build_required": False,
            "requires_confirmation": False,
            "local_changes": None,
            "staging_only": project.staging_only,
            "dry_run": True,
            "error": error,
        }

    # -- update -----------------------------------------------------------------------

    def update(self, project_id: str, *, confirm: bool = False, dry_run: bool = False) -> dict[str, Any]:
        project = self._require(project_id)
        if dry_run:
            return self.check(project_id)

        plan = self._build_plan(project, dry_run=False)
        if plan["status"] == "error":
            self.history.add({"project": project.id, "old_version": plan["current"].get("version"),
                              "new_version": None, "result": "failed", "error": plan["error"],
                              "build_result": None, "health_result": None})
            return {"ok": False, "project_id": project.id, "result": "failed",
                    "error": plan["error"], "status": "error"}

        if plan["status"] == "up-to-date":
            self._log_ok(f"{project.id} is already up to date")
            return {"ok": True, "project_id": project.id, "result": "up-to-date",
                    "status": "up-to-date", "old_version": plan["current"].get("version"),
                    "new_version": plan["available"].get("version") if plan.get("available") else plan["current"].get("version")}

        if plan["status"] == "no-stable-release":
            note = plan.get("note") or "no stable release is published"
            self._log_warn(f"{project.id}: {note}")
            return {"ok": False, "project_id": project.id, "result": "no-stable-release",
                    "status": "no-stable-release", "error": note,
                    "old_version": plan["current"].get("version"),
                    "new_version": None}

        if plan["status"] == "newer-than-remote":
            raise UpdateManagerError(f"local {project.id} is newer than the remote; nothing to update")

        if plan.get("requires_confirmation") and not confirm:
            local = plan.get("local_changes") or {}
            if local.get("detected"):
                reason = "local changes detected"
            elif not local.get("tracked"):
                reason = "installation is not tracked by the update manager"
            elif plan.get("development"):
                reason = "this is a development build (no stable release/tag)"
            else:
                reason = "confirmation required"
            raise UpdateManagerError(
                f"update for '{project.id}' requires confirmation ({reason}). "
                "Pass confirm=true after reviewing what will be overwritten.")

        old_version = plan["current"].get("version")
        new_ref = (plan.get("available") or {}).get("ref")
        new_version = (plan.get("available") or {}).get("version")

        # 1. backup
        backup_id = None
        try:
            self._log_info(f"backing up {project.id}")
            backup_id = self.backup.create(project, version_info={
                "old_version": old_version, "new_ref": new_ref, "new_version": new_version})
        except (OSError, ValueError) as exc:
            self.history.add({"project": project.id, "old_version": old_version,
                              "new_version": new_version, "result": "failed", "error": f"backup failed: {exc}",
                              "build_result": None, "health_result": None})
            return {"ok": False, "project_id": project.id, "result": "failed",
                    "error": f"backup failed: {exc}"}

        self._log_info(f"downloading {project.id} -> {new_ref}")
        source = self.source_for(project)
        staged: Optional[Path] = None
        try:
            staged = source.download(project, new_ref)
            _validate_staged(project, staged)
        except UpdateSourceError as exc:
            self._fail(project, old_version, new_version, backup_id, f"download failed: {exc}")
            return {"ok": False, "project_id": project.id, "result": "failed",
                    "error": f"download failed: {exc}", "backup_id": backup_id}

        try:
            if project.staging_only:
                result = self._apply_staged(project, staged, new_ref, new_version,
                                            old_version, backup_id, plan)
            else:
                result = self._apply_in_place(project, staged, new_ref, new_version,
                                              old_version, backup_id, plan)
            return result
        except (UpdateSourceError, OSError) as exc:
            # OSError included so a filesystem failure mid-apply can never
            # leave the component half-updated without a rollback attempt.
            self._log_err(f"update failed for {project.id}: {exc}")
            rolled = self._auto_rollback(project, backup_id, old_version, new_version, str(exc))
            rolled_ok = bool(rolled.get("restored"))
            result = "rolled-back" if rolled_ok else "rollback-failed"
            return {"ok": False, "project_id": project.id, "result": result,
                    "error": str(exc), "backup_id": backup_id,
                    "rollback": rolled, "rollback_failed": not rolled_ok}

    # -- apply: staging-only (JPNH core) ------------------------------------------

    def _apply_staged(self, project: ProjectManifest, staged: Path, new_ref: str,
                      new_version: Any, old_version: Any, backup_id: str,
                      plan: dict) -> dict[str, Any]:
        dest = update_cache_dir() / f"{project.id}-{new_ref[:12]}"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(staged), str(dest))

        # validate the staged content the same way a real apply would
        missing = [f for f in project.required_files if not (dest / f).exists()]
        if missing:
            shutil.rmtree(dest, ignore_errors=True)
            raise UpdateSourceError(
                f"staged update for {project.id} is missing required files: {', '.join(missing)}")
        staged_version = None
        if project.current_version_file:
            staged_version = parse_version_from_file(dest / project.current_version_file)
        if new_version and staged_version and str(new_version) != str(staged_version):
            shutil.rmtree(dest, ignore_errors=True)
            raise UpdateSourceError(
                f"staged update version mismatch: expected {new_version}, archive has {staged_version}")

        self.state.set(project.id, installed_ref=None, installed_version=None,
                       installed_fingerprint=None,
                       staged_ref=new_ref, staged_version=new_version,
                       staged_path=str(dest), updated_at=_now_iso(),
                       last_check=_now_iso(), last_error=None)
        self.history.add({"project": project.id, "old_version": old_version,
                          "new_version": new_version, "result": "staged",
                          "backup_id": backup_id, "rollback_status": None,
                          "build_result": None,
                          "health_result": {"ok": True, "checks": []}})
        self._log_ok(f"{project.id} staged version {new_version or new_ref} "
                     "(apply on next launch / manual checkout)")
        return {"ok": True, "project_id": project.id, "result": "staged",
                "status": "staged", "old_version": old_version,
                "new_version": new_version, "backup_id": backup_id,
                "staged_path": str(dest), "health": {"ok": True, "checks": []},
                "note": "Staged. The running JPNH is never replaced in place; "
                        "apply the staged checkout manually or via a new release."}

    # -- apply: in place (vendored components) --------------------------------------

    def _apply_in_place(self, project: ProjectManifest, staged: Path, new_ref: str,
                        new_version: Any, old_version: Any, backup_id: str,
                        plan: dict) -> dict[str, Any]:
        install_dir = project.install_dir(self.root)
        if project.install_path in ("", "."):
            raise UpdateSourceError("refusing to replace the repository root in place")

        # verify staged content is sane before touching the install dir
        checks = self.health.run(project, backend_alive=True, expected_version=new_version)
        if not checks["ok"]:
            raise UpdateSourceError(f"staged source failed validation: {_health_detail(checks)}")

        new_fingerprint = tree_fingerprint(staged, project)
        new_hashes = file_hashes(staged, project)

        self._log_info(f"applying {project.id}@{new_ref[:12]} to {install_dir}")
        if install_dir.exists():
            shutil.rmtree(install_dir)
        install_dir.mkdir(parents=True, exist_ok=True)
        for item in staged.iterdir():
            shutil.move(str(item), str(install_dir / item.name))

        self._write_metadata(project, {
            "source_type": project.source_type,
            "repository": project.repository,
            "ref": new_ref,
            "ref_type": (plan.get("available") or {}).get("ref_type", "commit"),
            "version": new_version,
            "installed_fingerprint": new_fingerprint,
            "installed_hashes": new_hashes,
            "updated_at": _now_iso(),
        })

        build_result = self._build(project)
        if build_result and build_result.get("failed"):
            raise UpdateSourceError(f"build failed: {build_result.get('error')}")

        health = self.health.run(project, backend_alive=True, expected_version=new_version)
        if not health["ok"]:
            raise UpdateSourceError(f"health check failed after update: {_health_detail(health)}")

        self.history.add({"project": project.id, "old_version": old_version,
                          "new_version": new_version, "result": "success",
                          "backup_id": backup_id, "rollback_status": None,
                          "build_result": build_result,
                          "health_result": {"ok": bool(health.get("ok")),
                                            "checks": health.get("checks", [])}})
        self._log_ok(f"{project.id} updated to {new_version or new_ref} (backup {backup_id})")
        return {"ok": True, "project_id": project.id, "result": "success",
                "status": "updated", "old_version": old_version,
                "new_version": new_version, "backup_id": backup_id,
                "build": build_result or {"ran": False},
                "health": health}

    def _build(self, project: ProjectManifest) -> Optional[dict[str, Any]]:
        """Run the declared build strategy; returns status dict or None."""
        if project.build_strategy == "none" and not project.build_command:
            return None
        if project.build_command:
            return self._run_command(project.build_command, project)
        if project.build_strategy == "network-checker":
            return self._build_network_checker()
        if project.build_strategy == "jpnh":
            return self._build_backend()
        return {"ran": False, "failed": False, "detail": "no build step"}

    def _build_network_checker(self) -> dict[str, Any]:
        platform = "win" if sys.platform.startswith("win") else "linux"
        script = self.root / "desktop" / "build" / "scripts" / "build-network-checker.mjs"
        if not script.exists():
            return {"ran": False, "failed": True, "error": "build script not found"}
        node = shutil.which("node") or "node"
        try:
            res = subprocess.run([node, str(script), platform], cwd=self.root,
                                 capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            return {"ran": True, "failed": True, "error": "build timed out"}
        if res.returncode != 0:
            return {"ran": True, "failed": True,
                    "error": (res.stderr or res.stdout or "build failed")[-2000:]}
        return {"ran": True, "failed": False, "detail": f"bundled for {platform}"}

    def _build_backend(self) -> dict[str, Any]:
        platform = "win" if sys.platform.startswith("win") else "linux"
        script = self.root / "desktop" / "build" / "scripts" / "build-backend.mjs"
        if not script.exists():
            return {"ran": False, "failed": True, "error": "build script not found"}
        node = shutil.which("node") or "node"
        try:
            res = subprocess.run([node, str(script), platform], cwd=self.root,
                                 capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            return {"ran": True, "failed": True, "error": "build timed out"}
        if res.returncode != 0:
            return {"ran": True, "failed": True,
                    "error": (res.stderr or res.stdout or "build failed")[-2000:]}
        return {"ran": True, "failed": False, "detail": f"backend bundled for {platform}"}

    def _run_command(self, command: str, project: ProjectManifest) -> dict[str, Any]:
        cwd = project.install_dir(self.root)
        try:
            res = subprocess.run(command, shell=True, cwd=cwd,
                                 capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            return {"ran": True, "failed": True, "error": "command timed out"}
        if res.returncode != 0:
            return {"ran": True, "failed": True,
                    "error": (res.stderr or res.stdout or "command failed")[-2000:]}
        return {"ran": True, "failed": False, "detail": "command completed"}

    # -- update all ----------------------------------------------------------------

    def update_all(self, *, confirm: bool = False, dry_run: bool = False) -> dict[str, Any]:
        """Check every project, update the safe ones, skip unsafe, summarize."""
        if dry_run:
            return self.dry_run()

        summary = []
        for project in self.registry.list():
            entry = {
                "project_id": project.id,
                "name": project.name,
                "status": None,
                "error": None,
                "old_version": None,
                "new_version": None,
                "backup_id": None,
            }
            try:
                plan = self._build_plan(project, dry_run=False)
            except UpdateManagerError as exc:
                entry["status"] = "skipped"
                entry["error"] = str(exc)
                summary.append(entry)
                continue
            if plan["status"] in ("error", "unknown", "missing"):
                entry["status"] = "skipped"
                entry["error"] = plan["error"] or {
                    "error": "check failed", "unknown": "unknown status",
                    "missing": "project is not installed",
                }.get(plan["status"])
                summary.append(entry)
                continue
            if plan["status"] == "up-to-date":
                entry["status"] = "current"
                summary.append(entry)
                continue
            if plan["status"] == "no-stable-release":
                entry["status"] = "no-stable-release"
                entry["error"] = plan.get("note") or "no stable release is published"
                summary.append(entry)
                continue
            if plan.get("requires_confirmation"):
                entry["status"] = "skipped"
                local = plan.get("local_changes") or {}
                if local.get("detected"):
                    entry["error"] = "local changes detected"
                elif not local.get("tracked"):
                    entry["error"] = "installation is not tracked by the update manager"
                elif plan.get("development"):
                    entry["error"] = "development build; not applied automatically"
                else:
                    entry["error"] = "confirmation required"
                summary.append(entry)
                continue
            try:
                result = self.update(project.id, confirm=True)
                entry["status"] = result.get("result", "done")
                entry["old_version"] = result.get("old_version")
                entry["new_version"] = result.get("new_version")
                entry["backup_id"] = result.get("backup_id")
                if not result.get("ok"):
                    entry["error"] = result.get("error")
            except UpdateManagerError as exc:
                entry["status"] = "failed"
                entry["error"] = str(exc)
            summary.append(entry)

        return {"summary": summary}

    # -- rollback ---------------------------------------------------------------------

    def rollback(self, backup_id: str) -> dict[str, Any]:
        info = self.backup.get(backup_id)
        if not info:
            raise UpdateManagerError(f"backup not found: {backup_id}")
        from .backup import _read_json
        meta = _read_json(Path(info["path"]) / "metadata.json") or {}
        project_data = meta.get("project")
        if not project_data:
            raise UpdateManagerError(f"backup {backup_id} has no project metadata")
        project = ProjectManifest.from_dict(project_data)
        version_info = meta.get("version_info") or {}

        self._log_info(f"rolling back {project.id} from backup {backup_id}")
        try:
            restored = self.backup.restore(backup_id, project)
        except (OSError, ValueError) as exc:
            raise UpdateManagerError(f"rollback failed: {exc}") from exc

        old_version = version_info.get("old_version")
        build_result = None
        if restored.get("project_restored"):
            build_result = self._rebuild_after_rollback(project)
        health = self.health.run(project, backend_alive=True)
        rollback_ok = restored["project_restored"] or not project.install_path
        if build_result and build_result.get("failed"):
            rollback_ok = False
        self.history.add({"project": project.id,
                          "old_version": version_info.get("new_version"),
                          "new_version": old_version,
                          "result": "rolled-back",
                          "backup_id": backup_id,
                          "rollback_status": "ok" if rollback_ok else "degraded",
                          "build_result": build_result,
                          "health_result": {"ok": bool(health.get("ok")),
                                            "checks": health.get("checks", [])}})
        self._log_ok(f"rollback complete for {project.id} (backup {backup_id})")
        return {
            "ok": rollback_ok,
            "project_id": project.id,
            "backup_id": backup_id,
            "restored": restored,
            "build": build_result,
            "health": health,
            "error": None if rollback_ok else (
                "project directory was not fully restored"
                if not restored.get("project_restored") else
                "component could not be rebuilt after rollback"),
        }

    # -- misc ---------------------------------------------------------------------------

    def _require(self, project_id: str) -> ProjectManifest:
        project = self.registry.get(project_id)
        if not project:
            raise UpdateManagerError(f"unknown project '{project_id}'")
        return project

    def _fail(self, project: ProjectManifest, old_version: Any, new_version: Any,
              backup_id: str, error: str) -> None:
        self.history.add({"project": project.id, "old_version": old_version,
                          "new_version": new_version, "result": "failed",
                          "error": error, "backup_id": backup_id,
                          "rollback_status": None,
                          "build_result": None, "health_result": None})
        self._log_err(f"update failed for {project.id}: {error}")

    def _auto_rollback(self, project: ProjectManifest, backup_id: str,
                       old_version: Any, new_version: Any, error: str) -> dict:
        try:
            restored = self.backup.restore(backup_id, project)
            build_result = None
            if restored.get("project_restored"):
                build_result = self._rebuild_after_rollback(project)
            health = self.health.run(project, backend_alive=True)
            rollback_ok = restored.get("project_restored", False) or not project.install_path
            if build_result and build_result.get("failed"):
                rollback_ok = False
            self.history.add({"project": project.id, "old_version": old_version,
                              "new_version": new_version, "result": "rolled-back",
                              "error": error, "backup_id": backup_id,
                              "rollback_status": "ok" if rollback_ok else "degraded",
                              "build_result": build_result,
                              "health_result": {"ok": bool(health.get("ok")),
                                                "checks": health.get("checks", [])}})
            self._log_warn(f"{project.id} automatically rolled back to backup {backup_id}")
            return {"restored": rollback_ok, "build": build_result, "health": health,
                    "error": None if rollback_ok else "component not fully restored after rollback"}
        except Exception as exc:  # pragma: no cover - defensive
            self._log_err(f"automatic rollback failed for {project.id}: {exc}")
            return {"restored": False, "error": f"rollback failed: {exc}"}

    def _rebuild_after_rollback(self, project: ProjectManifest) -> Optional[dict[str, Any]]:
        """Rebuild a component after its source was restored, so the built
        artifact (e.g. the bundled Network Checker) matches the restored tree.

        Never raises: a rebuild failure is reported, not fatal.
        """
        if project.build_strategy == "none" and not project.build_command:
            return None
        try:
            result = self._build(project)
        except Exception as exc:  # pragma: no cover - defensive
            return {"ran": False, "failed": True, "error": str(exc)}
        if result and result.get("failed"):
            self._log_err(f"rebuild after rollback failed for {project.id}: {result.get('error')}")
        return result


# ---------------------------------------------------------------------------
# module helpers
# ---------------------------------------------------------------------------

def _validate_staged(project: ProjectManifest, staged: Path) -> None:
    for rel in project.required_files:
        if not (staged / rel).exists():
            raise UpdateSourceError(
                f"downloaded source for '{project.id}' is missing '{rel}' — refusing to use it")


def _health_detail(health: dict) -> str:
    failed = [f"{c['name']}: {c['detail']}" for c in health.get("checks", []) if not c.get("ok")]
    return "; ".join(failed) if failed else "unknown"


def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


__all__ = ["UpdateManager", "UpdateManagerError", "current_jpnh_version"]