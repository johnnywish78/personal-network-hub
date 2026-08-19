"""Update source strategies.

Each source knows how to *check* what the upstream offers and *download*
the update content for a project. This is the extension point for future
component types: implementing a new :class:`UpdateSource` (and mapping it in
:class:`UpdateManager`) is all that is required to support a new mechanism.

Network access uses ``trust_env=True`` so the process honours standard
``HTTP_PROXY``/``HTTPS_PROXY``/``ALL_PROXY``/``NO_PROXY`` environment
variables when the user activates a terminal proxy. No proxy is ever
hard-coded and nothing here persists or exposes proxy credentials.
"""

from __future__ import annotations

import hashlib
import io
import tarfile
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import httpx

from .manifest import ProjectManifest
from .versions import strip_tag

API_BASE = "https://api.github.com"
CODE_LOAD = "https://codeload.github.com"

USER_AGENT = "JPNH-UpdateManager"

DEFAULT_EXCLUDE = {
    "build", ".dart_tool", ".git", ".flutter-plugins-dependencies",
    "node_modules", "dist", ".venv", "venv", "__pycache__",
    ".jpnh-update.json",
}


class UpdateSourceError(Exception):
    """Human-readable update failure. Never contains secrets."""


class UpdateSource(ABC):
    """Strategy interface: check + download for one project source type."""

    @abstractmethod
    def check_available(self, manifest: ProjectManifest) -> dict[str, Any]:
        """Return what upstream offers:

        {
          "ref": <commit sha or tag>,
          "ref_type": "commit" | "tag",
          "version": <human version string or None>,
          "release_tag": <latest release tag or None>,
          "published_at": <iso or None>,
          "url": <html url or None>,
        }
        """

    @abstractmethod
    def download(self, manifest: ProjectManifest, ref: str) -> Path:
        """Download + extract the source for `ref` into a fresh staging dir."""

    def fingerprint(self, directory: Path, manifest: ProjectManifest) -> str:
        """Content hash of a directory (excluding build/generated dirs)."""
        return tree_fingerprint(directory, manifest)


class GitHubSource(UpdateSource):
    """GitHub-based source: releases, tags, and commit archives.

    Used for both ``github`` and ``git`` source types (the archive download
    mechanism needs no git binary and no SSH keys). Stable releases/tags are
    preferred; development commits are only used when explicitly requested.
    """

    def __init__(self, http: Optional[httpx.Client] = None, timeout: float = 30.0):
        self._timeout = timeout
        self._http = http or _build_client(timeout)

    # -- network primitives (monkeypatch these in tests) ---------------------

    def api_json(self, url: str, params: Optional[dict] = None) -> Any:
        try:
            resp = self._http.get(url, params=params)
        except httpx.HTTPError as exc:
            raise UpdateSourceError(_network_message(exc)) from exc
        if resp.status_code in (401, 403):
            raise UpdateSourceError(
                "GitHub rejected the request (rate limit or missing auth). "
                "Retry later or set a GitHub token in the vault.")
        if resp.status_code == 429:
            raise UpdateSourceError(
                "GitHub rate limit reached. Retry in a few minutes.")
        if resp.status_code == 404:
            raise UpdateSourceError(f"GitHub resource not found: {url.split('/repos/')[-1]}")
        if 500 <= resp.status_code < 600:
            raise UpdateSourceError(
                f"GitHub server error (HTTP {resp.status_code}) for {url.split('/repos/')[-1]}")
        if resp.status_code != 200:
            raise UpdateSourceError(f"GitHub returned HTTP {resp.status_code} for {url}")
        try:
            return resp.json()
        except ValueError as exc:
            raise UpdateSourceError("GitHub returned an unparseable response") from exc

    def _repo_api(self, repo: str, suffix: str) -> str:
        return f"{API_BASE}/repos/{repo}{suffix}"

    def raw_file(self, repo: str, ref: str, path: str) -> Optional[str]:
        """Fetch a raw file's text from a ref (best-effort, for version detection)."""
        url = f"https://raw.githubusercontent.com/{repo}/{ref}/{path.lstrip('/')}"
        try:
            resp = self._http.get(url)
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        return resp.text

    # -- checks ---------------------------------------------------------------

    def check_available(self, manifest: ProjectManifest) -> dict[str, Any]:
        repo = manifest.repository or ""
        info: dict[str, Any] = {"ref": None, "ref_type": "commit",
                                "version": None, "release_tag": None,
                                "published_at": None, "url": f"https://github.com/{repo}",
                                "development": False}

        # Always verify the repository itself first. This makes error
        # classification unambiguous: a missing/private repository, an auth or
        # rate-limit rejection, and a network/proxy failure are each reported
        # distinctly, never as a misleading "commits/ref not found".
        try:
            repo_data = self.api_json(self._repo_api(repo, ""))
        except UpdateSourceError as exc:
            if "resource not found" in str(exc):
                raise UpdateSourceError(
                    f"repository not found or not publicly accessible: {repo}") from exc
            raise
        default_branch = manifest.branch or repo_data.get("default_branch")

        if manifest.tag:
            info.update(self._tag_info(repo, manifest.tag, default_branch))
            self._attach_file_version(manifest, info)
            return info

        if manifest.release_only:
            # 1. stable release
            try:
                release = self.api_json(self._repo_api(repo, "/releases/latest"))
                tag = release.get("tag_name")
                if not tag:
                    raise UpdateSourceError("release has no tag")
                info.update(self._tag_info(repo, tag, default_branch, release=release))
                self._attach_file_version(manifest, info)
                return info
            except UpdateSourceError:
                pass
            # 2. stable tag
            try:
                tags = self.api_json(self._repo_api(repo, "/tags"), params={"per_page": 10})
            except UpdateSourceError:
                tags = []
            if tags:
                tag = tags[0].get("name")
                info.update(self._tag_info(repo, tag, default_branch))
                self._attach_file_version(manifest, info)
                return info
            # 3. clearly defined stable-branch fallback: report it, never
            # silently present a branch head as a stable release.
            info["development"] = True
            info["version"] = None
            info["note"] = ("Repository reachable, but no stable release is published. "
                            "The default branch head is a development build.")
            info.update(self._head_commit(repo, default_branch or "main"))
            self._attach_file_version(manifest, info)
            return info

        commit = self._head_commit(repo, default_branch)
        info.update(commit)
        self._attach_file_version(manifest, info)
        return info

    def _attach_file_version(self, manifest: ProjectManifest, info: dict) -> None:
        """Best-effort: read the upstream version from the version file."""
        if manifest.version_detection not in ("file", "version_file"):
            return
        file_name = manifest.current_version_file
        if not file_name:
            return
        ref = info.get("ref")
        if not ref:
            return
        raw = self.raw_file(manifest.repository or "", ref, file_name)
        if raw is None:
            return
        from .sources import parse_version_text
        version = parse_version_text(raw, file_name.split("/")[-1])
        if version:
            info["version"] = version

    def _tag_info(self, repo: str, tag: Optional[str], default_branch: Optional[str],
                  release: Optional[dict] = None) -> dict[str, Any]:
        if not tag:
            raise UpdateSourceError(f"no tag found for {repo}")
        commit = None
        try:
            commit = self._head_commit(repo, tag)
        except UpdateSourceError:
            pass
        if commit is None:
            try:
                commit = self._head_commit(repo, default_branch or "main")
            except UpdateSourceError:
                commit = {}
        info: dict[str, Any] = {
            "ref": tag,
            "ref_type": "tag",
            "version": strip_tag(tag),
            "release_tag": tag,
            "published_at": (release or {}).get("published_at"),
        }
        info.update(commit or {})
        return info

    def _head_commit(self, repo: str, ref: str) -> dict[str, Any]:
        if not ref:
            raise UpdateSourceError(f"no default branch resolved for {repo}")
        try:
            data = self.api_json(self._repo_api(repo, f"/commits/{ref}"))
        except UpdateSourceError as exc:
            if "resource not found" in str(exc):
                raise UpdateSourceError(f"branch or ref '{ref}' not found in {repo}") from exc
            raise
        return {"ref": data.get("sha"),
                "ref_type": "commit",
                "version": None,
                "commit_sha": data.get("sha"),
                "published_at": (data.get("commit") or {}).get("committer", {}).get("date")}

    # -- download --------------------------------------------------------------

    def resolve_target(self, manifest: ProjectManifest) -> dict[str, Any]:
        """Choose the ref to update to (tag > release > branch head)."""
        available = self.check_available(manifest)
        if not available.get("ref"):
            raise UpdateSourceError(f"no updatable target resolved for {manifest.id}")
        return available

    def download(self, manifest: ProjectManifest, ref: str) -> Path:
        repo = manifest.repository or ""
        url = f"{CODE_LOAD}/{repo}/tar.gz/{ref}"
        staging = Path(tempfile.mkdtemp(prefix=f"jpnh-stage-{manifest.id}-"))
        archive = staging / "source.tar.gz"
        try:
            with self._http.stream("GET", url) as resp:
                if resp.status_code == 404:
                    raise UpdateSourceError(f"archive not found for {repo}@{ref} "
                                            "(release/tag may have been removed)")
                if resp.status_code in (401, 403):
                    raise UpdateSourceError(
                        "GitHub rejected the archive download (rate limit or auth). "
                        "Retry later or set a GitHub token in the vault.")
                if resp.status_code == 429:
                    raise UpdateSourceError("GitHub rate limit reached. Retry in a few minutes.")
                if resp.status_code != 200:
                    raise UpdateSourceError(
                        f"download failed for {repo}@{ref} (HTTP {resp.status_code})")
                with open(archive, "wb") as fh:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        fh.write(chunk)
            _extract_tarball(archive, staging)
        except httpx.HTTPError as exc:
            raise UpdateSourceError(_network_message(exc)) from exc
        finally:
            try:
                archive.unlink(missing_ok=True)
            except OSError:
                pass
        extracted = _first_subdir(staging)
        if extracted is None:
            raise UpdateSourceError(f"downloaded archive for {repo}@{ref} was empty or malformed")
        return extracted


class LocalSource(UpdateSource):
    """A managed-but-locally-defined project with no external source."""

    def check_available(self, manifest: ProjectManifest) -> dict[str, Any]:
        return {"ref": None, "ref_type": "none", "version": None,
                "release_tag": None, "published_at": None, "url": None}

    def download(self, manifest: ProjectManifest, ref: str) -> Path:
        raise UpdateSourceError("this project has no external update source")


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def _network_message(exc: Exception) -> str:
    msg = str(exc)
    if not msg:
        return "network error while contacting the remote source"
    low = msg.lower()
    if "timed out" in low:
        return "connection timed out while contacting the remote source"
    if "connection refused" in low or "connecterror" in low.replace(" ", ""):
        return "connection refused while contacting the remote source"
    if "name or service" in low or "getaddrinfo" in low:
        return "could not resolve the remote source host"
    if "proxy" in low:
        return f"proxy error: {msg[:300]}"
    return f"network error: {msg[:300]}"


def _build_client(timeout: float) -> httpx.Client:
    """Create an HTTP client that honours standard proxy env variables.

    ``HTTP_PROXY``/``HTTPS_PROXY``/``ALL_PROXY``/``NO_PROXY`` are respected.
    If the environment declares a proxy scheme this httpx build cannot use
    (for example ``socks://`` without the ``socksio`` package), fall back to
    a direct client so the update fails with a clear network error instead of
    crashing the whole application. Proxies are never hard-coded or persisted.
    """
    kwargs = dict(timeout=timeout, follow_redirects=True,
                  headers={"User-Agent": USER_AGENT})
    try:
        return httpx.Client(**kwargs, trust_env=True)
    except ValueError:
        try:
            return httpx.Client(**kwargs, trust_env=False)
        except ValueError:  # pragma: no cover - malformed env, last resort
            return httpx.Client(timeout=timeout)


def _extract_tarball(archive: Path, dest: Path) -> None:
    try:
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():
                _safe_member(member)
            try:  # Python >= 3.12: "data" filter blocks traversal, symlinks,
                  # hardlinks, absolute paths, and device/special files.
                tar.extractall(dest, filter="data")
            except TypeError:  # pragma: no cover - older Pythons
                tar.extractall(dest)
    except tarfile.TarError as exc:
        raise UpdateSourceError(f"downloaded archive is corrupted or not a valid tarball: {exc}") from exc


def _safe_member(member: tarfile.TarInfo) -> None:
    name = member.name
    if name.startswith("/") or ".." in Path(name).parts:
        raise UpdateSourceError("downloaded archive contains an unsafe path")
    if member.issym() or member.islnk():
        raise UpdateSourceError("downloaded archive contains a symlink or hard link")


def _first_subdir(staging: Path) -> Optional[Path]:
    subdirs = [p for p in staging.iterdir() if p.is_dir()]
    if len(subdirs) == 1:
        return subdirs[0]
    if not subdirs and any(p.is_file() for p in staging.iterdir()):
        return staging
    return staging


def tree_fingerprint(directory: Path, manifest: Optional[ProjectManifest] = None) -> str:
    """Deterministic content hash over a directory tree.

    Generated/build directories (and the manifest's excluded dirs) are
    skipped so that a rebuild does not look like a local modification.
    """
    excludes = set(DEFAULT_EXCLUDE)
    if manifest:
        excludes.update(str(e).strip("/") for e in manifest.exclude_backup)
    root = directory.resolve()
    hasher = hashlib.sha256()
    if not root.exists():
        return hasher.hexdigest()
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root)
        if any(rel.parts[0] == ex for ex in excludes):
            continue
        try:
            digest = _sha256_file(path)
        except OSError:
            continue
        hasher.update(rel.as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(digest)
    return hasher.hexdigest()


def _sha256_file(path: Path) -> bytes:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.digest()


def file_hashes(directory: Path, manifest: Optional[ProjectManifest] = None) -> dict[str, str]:
    """Map of relative path -> sha256 for a tree (excludes generated dirs).

    Used for precise local-change reporting (which files differ).
    """
    excludes = set(DEFAULT_EXCLUDE)
    if manifest:
        excludes.update(str(e).strip("/") for e in manifest.exclude_backup)
    root = directory.resolve()
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root)
        if any(rel.parts[0] == ex for ex in excludes):
            continue
        try:
            out[rel.as_posix()] = _sha256_file(path).hex()
        except OSError:
            continue
    return out


def parse_version_from_file(path: Path) -> Optional[str]:
    """Read a version string from a VERSION file or a pubspec-style file."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return parse_version_text(text, path.name)


def parse_version_text(text: str, filename: str = "") -> Optional[str]:
    """Extract a version string from raw file content (VERSION or YAML).

    pubspec versions may carry build metadata (``1.6.0+123``) or a ``v``
    prefix; both are normalized so the build suffix never changes a version.
    Malformed values return ``None`` instead of a bogus version.
    """
    if not text:
        return None
    if filename in ("pubspec.yaml", "pubspec.lock") or filename.endswith((".yaml", ".yml")):
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("version:") and " " in line:
                value = line.split(":", 1)[1].strip()
                value = value.split("+")[0].strip()
                return _normalize_version(value)
        return None
    first = text.splitlines()[0].strip() if text.splitlines() else None
    return _normalize_version(first) if first else None


def _normalize_version(value: str) -> Optional[str]:
    """Strip prefixes/build metadata and validate the semver core."""
    from .versions import Version, strip_tag
    if not value:
        return None
    norm = strip_tag(value)
    if not norm or not Version(norm):
        return None
    return norm