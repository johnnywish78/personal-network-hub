"""GitHub API client (first-class integration).

Uses the official GitHub REST API. Auth token is optional but recommended
for higher rate limits. Token is read from the secret vault at request
time; never logged.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx

API_BASE = "https://api.github.com"

DEFAULT_REPOS = {
    "BPB Worker Panel": {"repo": "bia-pain-bache/BPB-Worker-Panel", "kind": "cloudflare-worker"},
    "BPB Wizard": {"repo": "bia-pain-bache/BPB-Wizard", "kind": "tool"},
    "ZEUS": {"repo": "panel-zeus/Z-E-U-S", "kind": "panel"},
    "Aether GUI": {"repo": "MatinSenPai/Aether-GUI", "kind": "gui"},
    "Nova": {"repo": "IRNova/Nova-Proxy", "kind": "panel"},
    "Network Checker": {"repo": "mirarr-app/network-checker", "kind": "tool"},
}


class GitHubClient:
    def __init__(self, token_provider: Optional[callable] = None, timeout: float = 15.0):
        """token_provider is a callable returning the token or None."""
        self._token_provider = token_provider or (lambda: None)
        self._timeout = timeout

    def _headers(self) -> dict:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "JPNH"}
        token = self._token_provider()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        with httpx.Client(timeout=self._timeout, headers=self._headers(), follow_redirects=True, trust_env=False) as client:
            resp = client.get(f"{API_BASE}{path}", params=params)
            if resp.status_code == 404:
                raise GitHubError("not found")
            if resp.status_code == 401:
                raise GitHubError("authentication failed (token invalid or missing)")
            if resp.status_code == 403:
                raise GitHubError("rate limit exceeded or forbidden")
            resp.raise_for_status()
            return resp.json()

    def check(self) -> dict:
        """Status check used by the dashboard."""
        started = time.monotonic()
        try:
            user = self._get("/user") if self._token_provider() else {"login": "anonymous"}
            elapsed = round((time.monotonic() - started) * 1000, 1)
            return {"status": "ok", "latency_ms": elapsed, "authenticated": self._token_provider() is not None
                    and bool(self._token_provider()), "user": user.get("login"), "error": None}
        except (httpx.HTTPError, GitHubError) as exc:
            return {"status": "error", "latency_ms": None, "error": str(exc), "authenticated": False}

    def repo(self, full_name: str) -> dict:
        return self._get(f"/repos/{full_name}")

    def repos(self, full_names: Optional[list[str]] = None) -> list[dict]:
        """Fetch metadata for a list of repos. Each entry includes fetch errors."""
        names = full_names or [v["repo"] for v in DEFAULT_REPOS.values()]
        out = []
        for name in names:
            try:
                data = self.repo(name)
                out.append({
                    "full_name": data.get("full_name"),
                    "name": data.get("name"),
                    "description": data.get("description"),
                    "url": data.get("html_url"),
                    "default_branch": data.get("default_branch"),
                    "stargazers": data.get("stargazers_count"),
                    "forks": data.get("forks_count"),
                    "open_issues": data.get("open_issues_count"),
                    "language": data.get("language"),
                    "license": (data.get("license") or {}).get("spdx_id"),
                    "updated_at": data.get("updated_at"),
                    "fork": data.get("fork"),
                    "error": None,
                })
            except (httpx.HTTPError, GitHubError) as exc:
                out.append({"full_name": name, "name": name.split("/")[-1], "error": str(exc)})
        return out

    def branches(self, full_name: str) -> list[dict]:
        data = self._get(f"/repos/{full_name}/branches")
        return [{"name": b.get("name"), "protected": b.get("protected")} for b in data]

    def releases(self, full_name: str, per_page: int = 5) -> list[dict]:
        data = self._get(f"/repos/{full_name}/releases", params={"per_page": per_page})
        return [{
            "tag": r.get("tag_name"),
            "name": r.get("name"),
            "published_at": r.get("published_at"),
            "html_url": r.get("html_url"),
            "prerelease": r.get("prerelease"),
        } for r in data]

    def workflows(self, full_name: str) -> dict:
        data = self._get(f"/repos/{full_name}/actions/workflows")
        return {"workflows": [{
            "name": w.get("name"),
            "path": w.get("path"),
            "state": w.get("state"),
        } for w in data.get("workflows", [])], "total": data.get("total_count")}

    def workflow_runs(self, full_name: str, per_page: int = 5) -> list[dict]:
        data = self._get(f"/repos/{full_name}/actions/runs", params={"per_page": per_page})
        return [{
            "name": r.get("name"),
            "head_branch": r.get("head_branch"),
            "status": r.get("status"),
            "conclusion": r.get("conclusion"),
            "created_at": r.get("created_at"),
            "html_url": r.get("html_url"),
            "run_number": r.get("run_number"),
        } for r in data.get("workflow_runs", [])]

    def artifacts(self, full_name: str, per_page: int = 5) -> list[dict]:
        data = self._get(f"/repos/{full_name}/actions/artifacts", params={"per_page": per_page})
        return [{
            "name": a.get("name"),
            "size_in_bytes": a.get("size_in_bytes"),
            "created_at": a.get("created_at"),
            "expired": a.get("expired"),
        } for a in data.get("artifacts", [])]

    def issues(self, full_name: str, state: str = "open", per_page: int = 5) -> list[dict]:
        data = self._get(f"/repos/{full_name}/issues",
                         params={"state": state, "per_page": per_page})
        return [{
            "number": i.get("number"),
            "title": i.get("title"),
            "state": i.get("state"),
            "created_at": i.get("created_at"),
            "html_url": i.get("html_url"),
        } for i in data]

    def readme(self, full_name: str) -> dict:
        """Fetch README content (decoded to text)."""
        data = self._get(f"/repos/{full_name}/readme")
        content = data.get("content", "")
        try:
            import base64
            text = base64.b64decode(content).decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return {"name": data.get("name"), "size": data.get("size"),
                "content": text[:20000], "truncated": len(text) > 20000}

    def latest_release(self, full_name: str) -> dict:
        try:
            data = self._get(f"/repos/{full_name}/releases/latest")
        except GitHubError:
            return {"error": "no release found"}
        return {
            "tag": data.get("tag_name"),
            "name": data.get("name"),
            "published_at": data.get("published_at"),
            "html_url": data.get("html_url"),
            "body": (data.get("body") or "")[:4000],
            "prerelease": data.get("prerelease"),
        }


class GitHubError(Exception):
    pass
