"""JPNH - Johnny Personal Network Hub backend entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1 import (auth, checker, clients, cloudflare, configs, dashboard, github,
                     network, providers, railway, services, setup, system, updates,
                     xray)
from .services.state import app_state
from .version import get_version

VERSION = get_version()

app = FastAPI(
    title="Johnny Personal Network Hub",
    version=VERSION,
    description="Private network control center - orchestrates providers, configs, and clients.",
)

# Local personal application: the renderer runs from Electron (file:// or
# a local dev server). CORS is wide open for the local origin only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (dashboard, providers, cloudflare, railway, github,
               network, configs, xray, clients, auth, services, setup, system,
               checker, updates):
    if hasattr(module, "router"):
        app.include_router(module.router)
    for router in ("projects_router", "updates_router"):
        if hasattr(module, router):
            app.include_router(getattr(module, router))

app_state.logs.info("app", "JPNH backend loaded")


def _main() -> None:
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(prog="jpnh-backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    _main()


@app.get("/")
def root():
    return {"name": "Johnny Personal Network Hub", "codename": "JPNH", "docs": "/docs"}
