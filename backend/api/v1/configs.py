"""Config Hub API routes: import, parse, save, test, export, QR."""

from __future__ import annotations

import base64
import io
import json
from typing import Optional

import qrcode
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...configs import exporter as config_exporter
from ...configs import parser as config_parser
from ...configs.model import ConfigStatus, NormalizedConfig
from ...configs.normalizer import normalize
from ...configs.validator import validate
from ...network.config_test import test_config
from ...services.state import AppState
from .deps import get_state

router = APIRouter(prefix="/configs", tags=["configs"])


class ImportRequest(BaseModel):
    payload: str
    provider: Optional[str] = None
    source: Optional[str] = None


class UpdateRequest(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    address: Optional[str] = None
    port: Optional[int] = None
    tags: Optional[list[str]] = None
    group: Optional[str] = None


@router.patch("/{config_id}")
def update_config(config_id: str, body: UpdateRequest, state: AppState = Depends(get_state)):
    """Rename / tag / regroup / edit metadata. Never touches raw_config."""
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(400, "nothing to update")
    updated = state.config_store.update(config_id, **fields)
    if not updated:
        raise HTTPException(404, "config not found")
    state.logs.info("configs", f"updated metadata for '{updated.name}'")
    return {"ok": True, "config": updated.to_public_dict()}


@router.post("/{config_id}/duplicate")
def duplicate_config(config_id: str, state: AppState = Depends(get_state)):
    clone = state.config_store.duplicate(config_id)
    if not clone:
        raise HTTPException(404, "config not found")
    state.logs.info("configs", f"duplicated '{clone.name}'")
    return {"ok": True, "config": clone.to_public_dict()}


@router.get("")
def list_configs(state: AppState = Depends(get_state)):
    configs = state.config_store.list()
    return {"configs": [cfg.to_public_dict() for cfg in configs],
            "counts": state.config_store.counts()}


@router.get("/{config_id}")
def get_config(config_id: str, state: AppState = Depends(get_state)):
    cfg = state.config_store.get(config_id)
    if not cfg:
        raise HTTPException(404, "config not found")
    return cfg.to_public_dict()


@router.post("/import")
def import_configs(body: ImportRequest, state: AppState = Depends(get_state)):
    """Auto-detect and import payload: URIs, multiple URIs, JSON, subscription."""
    if not body.payload.strip():
        raise HTTPException(400, "empty payload")
    parsed = config_parser.parse_many(body.payload)
    if not parsed:
        raise HTTPException(400, "could not parse any configuration from payload")

    normalized: list[NormalizedConfig] = []
    errors: list[dict] = []
    for item in parsed:
        if "error" in item:
            errors.append({"error": item["error"]})
            continue
        cfg = normalize(item, provider=body.provider or item.get("source"),
                        source=body.source or item.get("source"))
        normalized.append(cfg)

    if body.provider and len(normalized) == 1:
        normalized[0].provider = body.provider

    added = state.config_store.add_many(normalized)
    state.logs.success("configs", f"imported {len(added)} configuration(s)")
    return {
        "ok": True,
        "imported": [cfg.to_public_dict() for cfg in added],
        "already_present": len(normalized) - len(added),
        "parse_errors": errors,
    }


@router.post("/parse")
def parse_payload(body: ImportRequest, state: AppState = Depends(get_state)):
    """Parse without saving. Returns normalized preview + validation."""
    if not body.payload.strip():
        raise HTTPException(400, "empty payload")
    parsed = config_parser.parse_many(body.payload)
    out = []
    for item in parsed:
        if "error" in item:
            out.append({"error": item["error"], "raw_config": item.get("raw_config", "")})
            continue
        cfg = normalize(item, provider=body.provider)
        validation = validate(cfg)
        out.append({"parsed": cfg.to_public_dict(), "validation": validation,
                    "validation_ok": validation["valid"]})
    return {"ok": True, "results": out}


@router.post("/{config_id}/test")
def test_one(config_id: str, state: AppState = Depends(get_state)):
    cfg = state.config_store.get(config_id)
    if not cfg:
        raise HTTPException(404, "config not found")
    state.config_store.update_status(config_id, ConfigStatus.TESTING)
    result = test_config(cfg)
    state.config_store.update_status(config_id, ConfigStatus(result["status"]),
                                     latency_ms=result.get("latency_ms"),
                                     error=result.get("error"))
    state.history.add({"config_id": config_id, "name": cfg.name, **result})
    state.logs.info("configs", f"tested '{cfg.name}': {result['result']}")
    return result


@router.post("/test")
def test_many(ids: list[str], state: AppState = Depends(get_state)):
    results = []
    for config_id in ids:
        cfg = state.config_store.get(config_id)
        if not cfg:
            results.append({"config_id": config_id, "error": "not found"})
            continue
        state.config_store.update_status(config_id, ConfigStatus.TESTING)
        result = test_config(cfg)
        state.config_store.update_status(config_id, ConfigStatus(result["status"]),
                                         latency_ms=result.get("latency_ms"),
                                         error=result.get("error"))
        state.history.add({"config_id": config_id, "name": cfg.name, **result})
        results.append(result)
    return {"results": results}


@router.post("/{config_id}/validate")
def validate_one(config_id: str, state: AppState = Depends(get_state)):
    cfg = state.config_store.get(config_id)
    if not cfg:
        raise HTTPException(404, "config not found")
    return {"validation": validate(cfg)}


@router.get("/{config_id}/uri")
def get_uri(config_id: str, state: AppState = Depends(get_state)):
    cfg = state.config_store.get(config_id)
    if not cfg:
        raise HTTPException(404, "config not found")
    uri = cfg.raw_config or config_exporter._preferred_uri(cfg)
    return {"ok": True, "uri": uri}


@router.get("/{config_id}/qr")
def get_qr(config_id: str, state: AppState = Depends(get_state)):
    cfg = state.config_store.get(config_id)
    if not cfg:
        raise HTTPException(404, "config not found")
    uri = cfg.raw_config or config_exporter._preferred_uri(cfg)
    if not uri:
        raise HTTPException(400, "no URI available for QR")
    qr = qrcode.QRCode(version=None, box_size=10, border=2)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return {"ok": True, "uri": uri, "png_base64": base64.b64encode(buf.getvalue()).decode("ascii")}


@router.delete("/{config_id}")
def delete_config(config_id: str, state: AppState = Depends(get_state)):
    deleted = state.config_store.delete(config_id)
    if not deleted:
        raise HTTPException(404, "config not found")
    state.logs.info("configs", f"deleted config {config_id}")
    return {"ok": True}


@router.get("/export/all")
def export_all(fmt: str = "txt", state: AppState = Depends(get_state)):
    configs = state.config_store.list()
    if not configs:
        raise HTTPException(400, "no configurations saved")
    return _export(configs, fmt)


@router.get("/{config_id}/export")
def export_one(config_id: str, fmt: str = "txt", state: AppState = Depends(get_state)):
    cfg = state.config_store.get(config_id)
    if not cfg:
        raise HTTPException(404, "config not found")
    return _export([cfg], fmt)


@router.get("/{config_id}/export/xray")
def export_xray(config_id: str, state: AppState = Depends(get_state)):
    cfg = state.config_store.get(config_id)
    if not cfg:
        raise HTTPException(404, "config not found")
    try:
        content = config_exporter.export_xray_config(cfg)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "filename": f"{cfg.name}.json", "content": content}


def _export(configs: list[NormalizedConfig], fmt: str) -> dict:
    fmt = fmt.lower()
    if fmt == "uri":
        content = config_exporter.export_uris(configs)
        filename = "configs.txt"
    elif fmt == "json":
        content = config_exporter.export_json(configs)
        filename = "configs.json"
    elif fmt == "txt":
        content = config_exporter.export_txt(configs)
        filename = "configs.txt"
    else:
        raise HTTPException(400, f"unsupported export format: {fmt}")
    return {"ok": True, "filename": filename, "content": content}
