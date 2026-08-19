"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends

from ...services.state import AppState, app_state


def get_state() -> AppState:
    return app_state
