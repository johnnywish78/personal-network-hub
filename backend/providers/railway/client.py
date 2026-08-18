"""Railway API client (first-class integration).

Railway has a public GraphQL API. We call it with the user's personal API
token. The token is provided by a token_provider (secret vault) at request
time and never logged. Secret variable values are never returned to the UI.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import httpx

API_URL = "https://backboard.railway.com/graphql/v2"
_RAILWAY_URL = "https://railway.com"


class RailwayClient:
    def __init__(self, token_provider: Optional[callable] = None, timeout: float = 20.0):
        self._token_provider = token_provider or (lambda: None)
        self._timeout = timeout

    def _headers(self) -> dict:
        token = self._token_provider()
        if not token:
            raise RailwayError("no API token configured")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _gql(self, query: str, variables: Optional[dict] = None) -> Any:
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables
        with httpx.Client(timeout=self._timeout, headers=self._headers(), follow_redirects=True, trust_env=False) as client:
            resp = client.post(API_URL, json=payload)
            if resp.status_code in (401, 403):
                raise RailwayError("authentication failed")
            if resp.status_code >= 500:
                raise RailwayError(f"Railway server error ({resp.status_code})")
            try:
                data = resp.json()
            except ValueError:
                raise RailwayError("invalid JSON response from Railway")
            if "errors" in data and data["errors"]:
                raise RailwayError(data["errors"][0].get("message", "GraphQL error"))
            return data.get("data")

    def check(self) -> dict:
        started = time.monotonic()
        try:
            self._gql("{ viewer { email username } }")
            elapsed = round((time.monotonic() - started) * 1000, 1)
            return {"status": "ok", "latency_ms": elapsed, "error": None}
        except RailwayError as exc:
            return {"status": "error", "latency_ms": None, "error": str(exc)}

    def projects(self) -> list[dict]:
        data = self._gql("""
            { projects(first: 100) { edges { node { id name description createdAt } } } }
        """)
        nodes = (data.get("projects") or {}).get("edges") or []
        return [{"id": n["node"]["id"], "name": n["node"].get("name"),
                 "description": n["node"].get("description"),
                 "url": f"{_RAILWAY_URL}/project/{n['node']['id']}"} for n in nodes]

    def services(self, project_id: str) -> list[dict]:
        data = self._gql("""
            query($id: ID!) {
              project(id: $id) { services { edges { node { id name } } } }
            }
        """, {"id": project_id})
        edges = (data.get("project") or {}).get("services") or {}
        nodes = edges.get("edges") or []
        return [{"id": n["node"]["id"], "name": n["node"].get("name")} for n in nodes]

    def deployments(self, project_id: str, service_id: Optional[str] = None) -> list[dict]:
        """List recent deployments for a project/service (metadata only)."""
        if service_id:
            query = """
                query($sid: ID!) {
                  deploymentList(serviceId: $sid) {
                    edges { node { id status createdAt } }
                  }
                }
            """
            variables = {"sid": service_id}
        else:
            query = """
                query($pid: ID!) {
                  project(id: $pid) { deployments { edges { node { id status createdAt service { name } } } } }
                }
            """
            variables = {"pid": project_id}
        data = self._gql(query, variables)
        edges = (data.get("deploymentList") or data.get("project", {}).get("deployments") or {}).get("edges") or []
        return [{
            "id": n["node"].get("id"),
            "status": n["node"].get("status"),
            "created_at": n["node"].get("createdAt"),
            "service": (n["node"].get("service") or {}).get("name"),
        } for n in edges]

    def domains(self, project_id: str) -> list[dict]:
        data = self._gql("""
            query($id: ID!) {
              project(id: $id) { domains { id domain service { name } } }
            }
        """, {"id": project_id})
        domains = (data.get("project") or {}).get("domains") or []
        return [{"id": d.get("id"), "domain": d.get("domain"),
                 "service": (d.get("service") or {}).get("name")} for d in domains]

    def variables_metadata(self, project_id: str, service_id: str) -> list[dict]:
        """Return variable NAMES only (redacted) for a service."""
        data = self._gql("""
            query($sid: ID!) {
              service(id: $sid) { variables }
            }
        """, {"sid": service_id})
        variables = (data.get("service") or {}).get("variables") or []
        return [{"name": key, "value_masked": "••••"} for key in sorted(variables.keys())]


class RailwayError(Exception):
    pass
