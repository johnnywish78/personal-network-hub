"""Service Registry API routes + browser favorites/tabs persistence."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...services.state import AppState
from .deps import get_state

router = APIRouter(prefix="/services", tags=["services"])


class ServiceCreate(BaseModel):
    name: str
    id: Optional[str] = None
    url: Optional[str] = None
    type: str = "tool"
    category: str = "custom"
    icon: str = "▧"
    open_mode: str = "embedded"


class ServicePatch(BaseModel):
    url: Optional[str] = None
    name: Optional[str] = None
    enabled: Optional[bool] = None
    open_mode: Optional[str] = None


class FavoritesBody(BaseModel):
    favorites: list[dict]


class TabsBody(BaseModel):
    tabs: list[dict]


@router.get("")
def list_services(state: AppState = Depends(get_state)):
    return {"services": state.service_list()}


@router.post("")
def add_service(body: ServiceCreate, state: AppState = Depends(get_state)):
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    service = state.services.add({
        "name": body.name.strip(),
        "id": (body.id or body.name).strip().lower().replace(" ", "-"),
        "url": (body.url or "").strip() or None,
        "type": body.type,
        "category": body.category,
        "icon": body.icon,
        "open_mode": body.open_mode,
    })
    state.logs.success("services", f"added service '{service['name']}'")
    return {"ok": True, "service": service}


@router.delete("/{service_id}")
def remove_service(service_id: str, state: AppState = Depends(get_state)):
    removed = state.services.remove(service_id)
    if not removed:
        raise HTTPException(404, "service not found")
    state.logs.info("services", f"removed service '{service_id}'")
    return {"ok": True}


@router.patch("/{service_id}")
def patch_service(service_id: str, body: ServicePatch, state: AppState = Depends(get_state)):
    updated = state.services.update(service_id, body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(404, "service not found")
    return {"ok": True, "service": updated}


@router.post("/{service_id}/enable")
def enable_service(service_id: str, state: AppState = Depends(get_state)):
    state.services.enable(service_id)
    return {"ok": True}


@router.post("/{service_id}/open")
def open_service(service_id: str, state: AppState = Depends(get_state)):
    result = state.open_service(service_id)
    if not result["ok"]:
        raise HTTPException(400, result.get("error") or "cannot open")
    return result


# --- Favorites / tabs (browser persistence, non-secret) ------------------

@router.get("/favorites")
def get_favorites(state: AppState = Depends(get_state)):
    return {"favorites": state.settings.get("browser.favorites", [])}


@router.put("/favorites")
def put_favorites(body: FavoritesBody, state: AppState = Depends(get_state)):
    state.settings.set("browser.favorites", body.favorites)
    return {"ok": True}


@router.post("/favorites")
def add_favorite(body: dict, state: AppState = Depends(get_state)):
    favorites = list(state.settings.get("browser.favorites", []))
    fav = {"id": body.get("id") or body.get("name"), "name": body.get("name"),
           "url": body.get("url"), "pinned": bool(body.get("pinned"))}
    favorites = [f for f in favorites if f.get("id") != fav["id"]]
    favorites.append(fav)
    state.settings.set("browser.favorites", favorites)
    return {"ok": True, "favorites": favorites}


@router.delete("/favorites/{fav_id}")
def remove_favorite(fav_id: str, state: AppState = Depends(get_state)):
    favorites = list(state.settings.get("browser.favorites", []))
    favorites = [f for f in favorites if f.get("id") != fav_id]
    state.settings.set("browser.favorites", favorites)
    return {"ok": True}


@router.get("/tabs")
def get_tabs(state: AppState = Depends(get_state)):
    return {"tabs": state.settings.get("browser.tabs", [])}


@router.put("/tabs")
def put_tabs(body: TabsBody, state: AppState = Depends(get_state)):
    state.settings.set("browser.tabs", body.tabs)
    return {"ok": True}