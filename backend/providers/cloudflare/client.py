"""Cloudflare API client (first-class integration).

Uses the official Cloudflare v4 REST API. The API token is provided by a
token_provider callable (from the secret vault) at request time and never
logged.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx

API_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareClient:
    def __init__(self, token_provider: Optional[callable] = None, timeout: float = 20.0):
        self._token_provider = token_provider or (lambda: None)
        self._timeout = timeout

    def _headers(self) -> dict:
        token = self._token_provider()
        if not token:
            raise CloudflareError("no API token configured")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        with httpx.Client(timeout=self._timeout, headers=self._headers(), follow_redirects=True, trust_env=False) as client:
            resp = client.get(f"{API_BASE}{path}", params=params)
            return self._handle(resp)

    def _post(self, path: str, payload: dict, params: Optional[dict] = None) -> Any:
        with httpx.Client(timeout=self._timeout, headers=self._headers(), follow_redirects=True, trust_env=False) as client:
            resp = client.post(f"{API_BASE}{path}", json=payload, params=params)
            return self._handle(resp)

    def _handle(self, resp: httpx.Response) -> Any:
        if resp.status_code in (401, 403):
            raise CloudflareError(f"authentication failed ({resp.status_code})")
        if resp.status_code == 429:
            raise CloudflareError("rate limited")
        if resp.status_code >= 500:
            raise CloudflareError(f"Cloudflare server error ({resp.status_code})")
        try:
            data = resp.json()
        except ValueError:
            raise CloudflareError(f"invalid response ({resp.status_code})")
        if not data.get("success"):
            errors = data.get("errors") or []
            msg = "; ".join(e.get("message", "unknown") for e in errors) or "request failed"
            raise CloudflareError(msg)
        return data.get("result")

    def check(self) -> dict:
        started = time.monotonic()
        try:
            self._get("/user/tokens/verify")
            elapsed = round((time.monotonic() - started) * 1000, 1)
            return {"status": "ok", "latency_ms": elapsed, "error": None}
        except CloudflareError as exc:
            return {"status": "error", "latency_ms": None, "error": str(exc)}

    def accounts(self) -> list[dict]:
        return self._get("/accounts")

    def zones(self, per_page: int = 50) -> list[dict]:
        data = self._get("/zones", params={"per_page": per_page})
        return [{
            "id": z.get("id"),
            "name": z.get("name"),
            "status": z.get("status"),
            "plan": (z.get("plan") or {}).get("name"),
        } for z in data]

    def zone_details(self, zone_id: str) -> dict:
        return self._get(f"/zones/{zone_id}")

    def workers(self, account_id: str) -> list[dict]:
        data = self._get(f"/accounts/{account_id}/workers/scripts")
        return [{
            "id": w.get("id"),
            "created_on": w.get("created_on"),
            "modified_on": w.get("modified_on"),
        } for w in data]

    def worker_script(self, account_id: str, name: str) -> dict:
        return self._get(f"/accounts/{account_id}/workers/scripts/{name}")

    def worker_versions(self, account_id: str, name: str) -> list[dict]:
        data = self._get(f"/accounts/{account_id}/workers/scripts/{name}/versions", params={"per_page": 5})
        return [{
            "id": v.get("id"),
            "created_on": v.get("created_on"),
        } for v in data]

    def pages_projects(self, account_id: str) -> list[dict]:
        data = self._get(f"/accounts/{account_id}/pages/projects")
        return [{
            "name": p.get("name"),
            "domains": p.get("domains", []),
            "subdomain": p.get("subdomain"),
            "updated_on": p.get("modified_on"),
            "url": p.get("url"),
        } for p in data]

    def pages_deployments(self, account_id: str, project: str) -> list[dict]:
        data = self._get(f"/accounts/{account_id}/pages/projects/{project}/deployments")
        return [{
            "id": d.get("id"),
            "environment": d.get("environment"),
            "created_on": d.get("created_on"),
            "url": d.get("url"),
            "latest_stage": d.get("latest_stage"),
        } for d in data]


class CloudflareError(Exception):
    pass
