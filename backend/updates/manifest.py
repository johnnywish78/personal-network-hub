"""Project manifest model for the Project Manager.

A manifest describes one installable/updatable project/component. Manifests
are **trusted local configuration** — they are never fetched from a remote
manifest, so a remote source can never dictate paths, build commands, or
update strategies. Fields are validated against allowlists to keep updates
conservative and path-traversal safe.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

SOURCE_TYPES = {"github", "git", "local", "none"}
UPDATE_STRATEGIES = {"download", "none"}
VERSION_DETECTION = {"version_file", "release", "commit", "file"}
BUILD_STRATEGIES = {"none", "network-checker", "jpnh"}
ROLLBACK_STRATEGIES = {"backup", "none"}

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")

# Keys that user-provided manifests may set. Anything else is rejected so a
# malformed or malicious project file cannot smuggle arbitrary fields in.
ALLOWED_KEYS = {
    "id", "name", "description", "enabled", "source_type", "repository",
    "branch", "tag", "install_path", "update_strategy", "build_strategy",
    "build_command", "post_update_command", "rollback_strategy",
    "version_detection", "current_version_file", "health_checks",
    "exclude_backup", "release_only", "staging_only", "required_files",
    "category", "icon",
}


def validate_project_id(project_id: str) -> str:
    project_id = str(project_id or "").strip()
    if not _ID_RE.match(project_id):
        raise ValueError(
            "invalid project id (use lowercase letters, digits, '-', '_', '.')"
        )
    return project_id


@dataclass
class ProjectManifest:
    """Trusted definition of one managed project/component."""

    id: str
    name: str
    description: str = ""
    enabled: bool = True
    source_type: str = "none"             # github | git | local | none
    repository: Optional[str] = None      # "owner/repo" for github/git
    branch: Optional[str] = None
    tag: Optional[str] = None
    install_path: str = ""                # repo-relative directory
    update_strategy: str = "download"
    build_strategy: str = "none"          # none | network-checker | jpnh
    build_command: Optional[str] = None   # optional explicit shell command
    post_update_command: Optional[str] = None
    rollback_strategy: str = "backup"
    version_detection: str = "version_file"
    current_version_file: Optional[str] = None
    health_checks: list[str] = field(default_factory=list)
    exclude_backup: list[str] = field(default_factory=list)
    release_only: bool = False            # only stable releases/tags, never dev commits
    staging_only: bool = False            # download+validate+stage, never apply in place
    required_files: list[str] = field(default_factory=list)
    category: str = "component"
    icon: str = "⇅"

    # ---- construction ------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, strict: bool = True) -> "ProjectManifest":
        if not isinstance(data, dict):
            raise ValueError("project manifest must be a dictionary")
        unknown = set(data) - ALLOWED_KEYS
        if strict and unknown:
            raise ValueError(f"unknown manifest keys: {', '.join(sorted(unknown))}")
        project_id = validate_project_id(data.get("id") or data.get("name") or "")
        return cls(
            id=project_id,
            name=str(data.get("name") or project_id),
            description=str(data.get("description") or ""),
            enabled=bool(data.get("enabled", True)),
            source_type=str(data.get("source_type") or "none"),
            repository=_clean_repository(data.get("repository")),
            branch=_clean_ref(data.get("branch")),
            tag=_clean_ref(data.get("tag")),
            install_path=_clean_relative_path(data.get("install_path") or ""),
            update_strategy=str(data.get("update_strategy") or "download"),
            build_strategy=str(data.get("build_strategy") or "none"),
            build_command=_clean_command(data.get("build_command")),
            post_update_command=_clean_command(data.get("post_update_command")),
            rollback_strategy=str(data.get("rollback_strategy") or "backup"),
            version_detection=str(data.get("version_detection") or "version_file"),
            current_version_file=_clean_relative_path(data.get("current_version_file")),
            health_checks=[str(h) for h in data.get("health_checks") or []],
            exclude_backup=[str(e) for e in data.get("exclude_backup") or []],
            release_only=bool(data.get("release_only", False)),
            staging_only=bool(data.get("staging_only", False)),
            required_files=[_clean_relative_path(f) for f in data.get("required_files") or []],
            category=str(data.get("category") or "component"),
            icon=str(data.get("icon") or "⇅"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "source_type": self.source_type,
            "repository": self.repository,
            "branch": self.branch,
            "tag": self.tag,
            "install_path": self.install_path,
            "update_strategy": self.update_strategy,
            "build_strategy": self.build_strategy,
            "build_command": self.build_command,
            "post_update_command": self.post_update_command,
            "rollback_strategy": self.rollback_strategy,
            "version_detection": self.version_detection,
            "current_version_file": self.current_version_file,
            "health_checks": list(self.health_checks),
            "exclude_backup": list(self.exclude_backup),
            "release_only": self.release_only,
            "staging_only": self.staging_only,
            "required_files": list(self.required_files),
            "category": self.category,
            "icon": self.icon,
        }

    def validate(self) -> None:
        """Validate against allowlists; raises ValueError on any violation."""
        validate_project_id(self.id)
        if self.source_type not in SOURCE_TYPES:
            raise ValueError(f"unsupported source_type '{self.source_type}'")
        if self.update_strategy not in UPDATE_STRATEGIES:
            raise ValueError(f"unsupported update_strategy '{self.update_strategy}'")
        if self.build_strategy not in BUILD_STRATEGIES:
            raise ValueError(f"unsupported build_strategy '{self.build_strategy}'")
        if self.rollback_strategy not in ROLLBACK_STRATEGIES:
            raise ValueError(f"unsupported rollback_strategy '{self.rollback_strategy}'")
        if self.version_detection not in VERSION_DETECTION:
            raise ValueError(f"unsupported version_detection '{self.version_detection}'")
        if self.source_type in ("github", "git") and not self.repository:
            raise ValueError(f"project '{self.id}': repository is required for {self.source_type} source")
        if self.branch and self.tag:
            raise ValueError(f"project '{self.id}': branch and tag are mutually exclusive")
        # Path safety: install_path must be a relative directory that stays
        # inside the repository root.
        _clean_relative_path(self.install_path)

    def install_dir(self, root: Path) -> Path:
        """Resolve the project directory, refusing path traversal."""
        path = root / self.install_path if self.install_path else root
        resolved = path.resolve()
        root_resolved = root.resolve()
        if not (resolved == root_resolved or root_resolved in resolved.parents):
            raise ValueError(f"project '{self.id}': install_path escapes repository root")
        return resolved


def _clean_repository(value: Any) -> Optional[str]:
    if not value:
        return None
    repo = str(value).strip().strip("/")
    if repo.startswith(("https://", "http://", "git@", "git://")):
        repo = repo.split("/")[-2] + "/" + repo.split("/")[-1] if "/" in repo else repo
    if "/" not in repo or len(repo.split("/")) != 2:
        raise ValueError(f"invalid repository '{repo}' (expected 'owner/repo')")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError(f"invalid repository '{repo}'")
    return repo


def _clean_ref(value: Any) -> Optional[str]:
    if value is None:
        return None
    ref = str(value).strip()
    if not ref or ref in {".", ".."} or "/" in ref or ref.startswith("-"):
        raise ValueError(f"invalid ref '{value}'")
    return ref


def _clean_relative_path(value: Any) -> Optional[str]:
    if value is None:
        return None
    p = str(value).strip().replace("\\", "/")
    if not p or p in {".", "/"}:
        return None
    if p.startswith("/") or ".." in Path(p).parts:
        raise ValueError(f"invalid relative path '{value}'")
    return p


def _clean_command(value: Any) -> Optional[str]:
    if value is None:
        return None
    cmd = str(value).strip()
    if not cmd:
        return None
    if ";" in cmd or "&&" in cmd or "||" in cmd or "`" in cmd or "$(" in cmd:
        raise ValueError("command chaining/shell injection is not allowed in manifests")
    return cmd