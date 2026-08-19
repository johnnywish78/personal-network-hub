# Johnny Personal Network Hub (JPNH)

A private, personal-use **Network Control Center** desktop application that unifies
access to your existing network/proxy projects in one clean interface.

JPNH is an **orchestrator**, not a client. It does **not** replace v2rayN,
Hiddify, V2Box, Aether, or Xray. It discovers, connects, manages, imports, parses,
validates, tests, stores, exports, and hands off configurations to those clients.

> **Absolute rule:** JPNH never modifies external projects. Existing panels,
> repositories, and deployments are opened and managed through official APIs,
> GitHub, or standard config formats — never rewritten.

---

## What's inside

| View | Purpose |
|------|---------|
| **Dashboard** | Internet, services, providers, configs, Xray, clients — one glance |
| **Browser** | Tab-based embedded browser (persistent sessions, favorites, restore tabs) |
| **Services** | Service Registry — add/remove/open any integrated service, live status |
| **Network** | DNS, TCP, TLS, latency, domain checks, clean-IP testing |
| **Network Checker** | Full toolset: diagnostics, protocols, domain/DNS checks, Edge IP, Akamai, VLESS modifier, Netlify generator, SNI Spoof Check, Cloudflare Fix, Chain, plus the bundled app launcher |
| **Configs** | Import/parse/validate/test/save/export configs + QR, rename/tag/duplicate/group |
| **Xray** | Detect, start/stop/restart, validate config (fully optional) |
| **Clients** | Detect v2rayN / Hiddify / V2Box and set executable paths |
| **Settings** | Theme (light/dark), masked credential overview |

Manager views (Providers, Cloudflare, Railway, GitHub) are reachable from the
Services page.

## Architecture

- **Electron** desktop shell (`desktop/`)
- **FastAPI** local backend (`backend/`), spawned by Electron on launch
- Provider **adapters** (`backend/providers/`) — thin, capability-accurate
- Config **parsers / normalizers** (`backend/configs/`) — VLESS, Trojan, VMess,
  Shadowsocks, Hysteria2, WireGuard, Xray/sing-box JSON
- **Test engine** (`backend/network/config_test.py`) — Parse → Validate → DNS →
  TCP → TLS → protocol check. Never marks a config WORKING just because a TCP
  port is open. OS-level errors are translated into human-readable messages
  (`backend/network/errors.py`).
- **Service Registry** (`backend/services/registry.py`) — every integrated
  service (GitHub, Cloudflare, Railway, BPB Worker Panel, BPB Wizard, ZEUS,
  RVG, Aether, Nova, Network Checker, Xray) is a first-class, user-editable
  entry with live status and an open action.
- **Bundled Network Checker** (`third_party/network-checker/`) — the ORIGINAL
  upstream Flutter app (mirarr-app/network-checker, GPL-3.0) is vendored
  unmodified and shipped as a managed child application. JPNH only launches
  and stops it; the upstream implementation is never rewritten.
- **Native Network Checker tools** (`backend/network/checker/`) — a pure-Python
  port of the upstream tool set exposed over `/checker/*`: Internet
  Diagnostics, Protocol Accessibility, Domain Check, DNS Latency, DNS Hunter,
  Edge IP scan, Akamai scan, VLESS Modifier, Netlify Generator, Xray Scan,
  SNI Spoof Check, Cloudflare Fix, and the Chain generator.
- **Credential store** (`backend/storage/credential_store.py`) — prefers the OS
  keyring when available, falls back to a 0600 local vault.

```
personal-network-hub/
├── backend/
│   ├── api/v1/            # FastAPI routes
│   ├── providers/         # bpb, zeus, rvg, aether, nova, cloudflare, railway, github
│   ├── network/           # dns, tcp, tls, latency, diagnostics, config_test
│   ├── configs/           # parser, normalizer, validator, storage, exporter
│   ├── xray/              # detector, manager, validator
│   ├── services/          # state, settings, vault access, logging, history,
│   │                      # network_checker (bundle resolution)
│   └── storage/           # paths, atomic JSON store, secret vault
├── desktop/               # Electron main/preload + renderer UI
│   ├── lib/               # backend-manager, network-checker-manager (pure Node)
│   └── build/scripts/     # build-backend.mjs, build-network-checker.mjs
├── third_party/network-checker/   # vendored upstream Flutter app (GPL-3.0)
├── resources/             # built artifacts bundled at package time
│   ├── backend/           # PyInstaller backend per platform
│   └── network-checker/   # built Flutter bundle per platform
├── tests/                 # pytest suite (85 tests)
├── scripts/run.sh         # one-command launcher
├── VERSION
└── requirements.txt
```

## Getting started

```bash
./scripts/run.sh
```

This creates a virtualenv, installs Python + Electron dependencies, starts the
backend on `http://127.0.0.1:8765`, and opens the desktop app.

### Running pieces separately

```bash
# Backend only
.venv/bin/python -m backend.main --host 127.0.0.1 --port 8765

# Desktop only (requires backend running, or it will try to start it)
cd desktop && npx electron . --no-sandbox
```

## Production packaging

Installable artifacts (no Python/Node/Flutter/terminal required at runtime) are
built with `electron-builder` plus PyInstaller for the backend and Flutter for
the bundled Network Checker.

```bash
# Linux (AppImage + deb)
cd desktop && npm run dist:linux

# Windows (NSIS installer) — must be run on a Windows machine
cd desktop && npm run dist:win
```

Outputs land in `dist/`:
- `Johnny Network Hub-0.1.0-linux-x86_64.AppImage`
- `Johnny Network Hub-0.1.0-linux-amd64.deb`
- `JPNH-Setup-<version>.exe` (Windows)

Individual steps: `npm run build:backend` (PyInstaller),
`npm run build:network-checker` (Flutter bundle), `npm run icons`
(avatar-derived icon set). The app icon is generated from the user avatar at
`desktop/renderer/assets/avatar.jpg`.

> **Windows:** PyInstaller, Flutter, and NSIS are not cross-compilable. `dist:win`
> must be executed on Windows; the configuration and scripts are provided but the
> Windows artifact is not built or tested from Linux.

## Security

- **No hard-coded credentials.** All tokens are entered through the UI and stored
  in the local vault (`~/.jpnh/secrets.json`, permissions `0600`).
- **No secrets in Git.** `.gitignore` excludes `.env`, `.jpnh/`, `secrets.json`.
- **No secrets in the frontend.** The API only returns *masked* key presence.
- **No secrets in logs.** The log hub redacts URIs before writing.
- API tokens are read from the vault at request time and never logged.

## Config status

Each configuration is labeled with one of:
`UNKNOWN · TESTING · WORKING · DEGRADED · FAILED`

with last-test time, latency, failure reason, provider, and protocol shown inline.

## Testing

```bash
.venv/bin/python -m pytest tests/ -q
```

Covers parsers (VLESS/Trojan/VMess/SS/JSON), normalization, validation, storage,
export, network diagnostics, provider adapters, Xray/client detection, Network
Checker bundle resolution, the `/checker/*` native tool API, and API contracts.

```bash
# Node tests for the pure-Node process managers
cd desktop && node --test test/*.test.js
```

## License & attribution

External projects are integrated through adapters and never copied into this
codebase. Their respective licenses are respected; provider metadata records the
source repository for each integration.

The bundled Network Checker is the **unmodified upstream** Flutter application
from [`mirarr-app/network-checker`](https://github.com/mirarr-app/network-checker)
(GPL-3.0), vendored under `third_party/network-checker/` for offline builds. Its
license, source, and attribution are preserved in that directory.

The native `/checker/*` Python tools in `backend/network/checker/` are a
**port** of the same GPL-3.0 upstream project's algorithms
(`lib/core/services/*_service.dart`); the file headers and
`backend/api/v1/checker.py` carry the attribution.

Version `0.1.0` — first release.
