"""GitHub API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...providers.github.client import DEFAULT_REPOS, GitHubError
from ...services.state import AppState
from .deps import get_state

router = APIRouter(prefix="/github", tags=["github"])


class TokenRequest(BaseModel):
    token: str


@router.get("/status")
def status(state: AppState = Depends(get_state)):
    gh = state.github.check()
    return {"configured": state.vault.has("github_token"), **gh}


@router.post("/auth")
def auth(body: TokenRequest, state: AppState = Depends(get_state)):
    token = body.token.strip()
    if not token:
        raise HTTPException(400, "token is required")
    state.vault.set("github_token", token)
    state.logs.success("github", "token saved (masked in vault)")
    return {"ok": True}


@router.delete("/auth")
def deauth(state: AppState = Depends(get_state)):
    state.vault.delete("github_token")
    state.logs.info("github", "token removed")
    return {"ok": True}


@router.get("/repos")
def repos(state: AppState = Depends(get_state)):
    return {"repos": state.github.repos(), "known": [
        {"name": name, **info} for name, info in DEFAULT_REPOS.items()
    ]}


@router.get("/repos/{full_name:path}/workflows")
def workflows(full_name: str, state: AppState = Depends(get_state)):
    full_name = full_name.strip("/")
    try:
        return {"workflows": state.github.workflows(full_name),
                "runs": state.github.workflow_runs(full_name)}
    except (GitHubError, Exception) as exc:
        raise HTTPException(502, str(exc))


@router.get("/repos/{full_name:path}/artifacts")
def artifacts(full_name: str, state: AppState = Depends(get_state)):
    full_name = full_name.strip("/")
    try:
        return {"artifacts": state.github.artifacts(full_name)}
    except (GitHubError, Exception) as exc:
        raise HTTPException(502, str(exc))


@router.get("/repos/{full_name:path}/issues")
def issues(full_name: str, state: AppState = Depends(get_state)):
    full_name = full_name.strip("/")
    try:
        return {"issues": state.github.issues(full_name)}
    except (GitHubError, Exception) as exc:
        raise HTTPException(502, str(exc))


@router.get("/repos/{full_name:path}/readme")
def readme(full_name: str, state: AppState = Depends(get_state)):
    full_name = full_name.strip("/")
    try:
        return state.github.readme(full_name)
    except (GitHubError, Exception) as exc:
        raise HTTPException(502, str(exc))


@router.get("/repos/{full_name:path}/releases/latest")
def latest_release(full_name: str, state: AppState = Depends(get_state)):
    full_name = full_name.strip("/")
    try:
        return state.github.latest_release(full_name)
    except (GitHubError, Exception) as exc:
        raise HTTPException(502, str(exc))


@router.get("/repos/{full_name:path}/open")
def open_repo(full_name: str, state: AppState = Depends(get_state)):
    """Open a repository page (handed to the Browser Hub)."""
    full_name = full_name.strip("/")
    return {"ok": True, "url": f"https://github.com/{full_name}", "action": "open"}


@router.get("/repos/{full_name:path}")
def repo_detail(full_name: str, state: AppState = Depends(get_state)):
    full_name = full_name.strip("/")
    try:
        return {
            "repo": state.github.repo(full_name),
            "branches": state.github.branches(full_name),
            "releases": state.github.releases(full_name),
        }
    except (GitHubError, Exception) as exc:
        raise HTTPException(502, str(exc))
