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
| **Updates** | Update Manager + Project Manager — check, dry-run, backup, and update JPNH core and managed components (GUI, API, and CLI) |
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
- **Update Manager** (`backend/updates/`) — versioned, backed-up, health-checked
  updates for JPNH core and managed projects. A **Project/Component Registry**
  (`backend/updates/registry.py`) is the single source of truth; built-ins are
  `jpnh-core` (download + validate + stage; never hot-swaps a running checkout)
  and `network-checker` (the vendored Flutter app), and additional projects can
  be added as user manifests in `<data_dir>/projects/*.json`. Every apply takes
  a state+project **backup**, and any failure (apply, build, or health check)
  triggers an **automatic rollback**. Git commands are never required — upstream
  sources are fetched as GitHub tarballs and verified by content hash.

```
personal-network-hub/
├── backend/
│   ├── api/v1/            # FastAPI routes
│   ├── providers/         # bpb, zeus, rvg, aether, nova, cloudflare, railway, github
│   ├── network/           # dns, tcp, tls, latency, diagnostics, config_test
│   ├── configs/           # parser, normalizer, validator, storage, exporter
│   ├── xray/              # detector, manager, validator
│   ├── updates/           # update manager, registry, sources, backup/rollback
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

## Update Manager

The **Updates** view manages JPNH core and every project/component in the
registry. All operations are also exposed over the API (`/updates`,
`/projects`) and a CLI that does not need the backend running.

```bash
# from anywhere in the checkout (repo root is auto-added to sys.path)
.venv/bin/python -m backend.updates.cli check          # live check, no changes
.venv/bin/python -m backend.updates.cli dry-run        # plan updates, no changes
.venv/bin/python -m backend.updates.cli dry-run <id>   # one project
.venv/bin/python -m backend.updates.cli status         # local state overview
.venv/bin/python -m backend.updates.cli update <id>    # update one project
.venv/bin/python -m backend.updates.cli update-all     # update all safe projects
.venv/bin/python -m backend.updates.cli history        # update history
.venv/bin/python -m backend.updates.cli backups        # list backups
.venv/bin/python -m backend.updates.cli rollback <backup_id>
```

Or from `desktop/` via npm: `npm run update:check`, `update:dry-run`,
`update`, `update:all`, `update:history`, `update:backups`.

Apply-on-restart for JPNH core (source/dev installs):
```bash
# stage the new core checkout, then apply it on the next start
.venv/bin/python -m backend.updates.apply_pending
# or clear a previously staged apply without applying it
.venv/bin/python -m backend.updates.apply_pending --clear
```

### How it works

- **Registry is the source of truth.** Built-ins are `jpnh-core` (this app) and
  `network-checker` (the vendored Flutter app, install path
  `third_party/network-checker`, version detected from `pubspec.yaml`, rebuilt
  with `build-network-checker.mjs`). Additional projects live in
  `<data_dir>/projects/*.json`; malformed manifests are skipped and reported
  rather than crashing, and a per-user file can never override a built-in
  project.
- **No git required.** Upstream sources are fetched as GitHub tarballs,
  fingerprint-checked, and extracted; a `.jpnh-update.json` metadata file
  records the applied ref/version and is excluded from fingerprints.
- **Automatic adoption / baselining.** An install that is present but not yet
  managed (no `.jpnh-update.json`) is *adopted* on the next scan: the existing
  tree is fingerprinted in place as the baseline, marked `adopted`, and
  displayed as **Managed** — with **no download and no modification of the
  files**. Dry-run/check operations never write adoption metadata; adoption is
  written only by a real scan/update. Once adopted, later local modifications
  are still detected against the baseline. Projects whose version cannot be
  determined, that live at the repo root, or that are not from a GitHub/git
  source are never adopted.
- **Status model.** A component is `up-to-date`, `update-available`,
  `installed` (present but not yet managed — the first update backs it up and
  tracks it), `missing` (not installed), `no-stable-release` (reachable, but
  no stable release or tag is published — never applied), `disabled`,
  `error`, or `newer-than-remote`. Plans carry a `note` when the upstream
  cannot be resolved to a stable release.
- **Honest error messages.** Upstream problems are classified instead of
  guessed: missing/private repositories report "repository not found or not
  publicly accessible", rate limits and auth rejections are called out
  separately, server errors and unparseable responses are distinguished, and
  every tarball member is checked against path traversal and symlink escape
  before extraction.
- **Safe by default.**
  - `jpnh-core` updates are always staged: downloaded, validated, health-checked,
    and recorded in update state — the running checkout is never replaced in
    place. **Activation is not automatic while a backend is running.** A source
    checkout can be activated on the *next application start* via the
    **Download & Stage → Restart & Update** flow: the backend writes a
    `.jpnh-pending-apply.json` marker, the app relaunches, and the updater swaps
    the staged checkout in (backing up the current tree to the rollback dir,
    health-checking, and rolling back if the swap fails). A packaged
    (AppImage/deb) install does not self-swap the source tree — it is updated
    from the packaged release instead.
  - **AppImage self-update keeps the Ubuntu menu launcher working.** While
    running as an AppImage, the Updates view offers **Download AppImage →
    Restart & Apply**: the release's `.AppImage` asset is downloaded into the
    update cache, SHA256-checked, and written to the pending-apply marker. On
    the next launch the startup updater resolves the *installed* AppImage — the
    file the desktop entry (`~/.local/share/applications/jpnh.desktop`) runs,
    falling back to `$APPIMAGE` — and atomically replaces it: the old binary is
    preserved as `<name>.old`, the new file is verified (exists, executable,
    SHA256 matches) before the swap is accepted, any failure restores the old
    binary, and the `<name>.old` is removed only after the new build has started
    successfully. The desktop entry is never edited, so the menu keeps launching
    the same stable path with no duplicate entries.
  - Untracked or locally-modified installs require explicit confirmation and
    are skipped by `update-all`.
  - Every apply creates a backup (state files + project copy, credential *keys*
    only — never secret values) under `<data_dir>/backups/<project>-<timestamp>/`.
    Backup manifests record the project, source, reason, backup id, timestamp,
    and old/new version and ref.
  - Apply, build, or health-check failures trigger an automatic rollback to the
    latest backup; rolling back a built component (e.g. Network Checker) rebuilds
    it afterwards and re-checks its health. Manual rollback is available via
    CLI/API/GUI.
- **Health checks** include required-files presence and a live backend API ping;
  for `network-checker` the bundle is also verified as a runnable Flutter asset.
  History entries record the build and health result of every operation.
- **VPN / proxy note.** JPNH has no built-in VPN and does not require one.
  Upstream checks honour standard proxy environment variables
  (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`), so you can activate a
  terminal proxy before running `update:check`.
- **JPNH core repository accessibility.** As of this writing the GitHub API
  reports `johnnywish78/personal-network-hub` as not publicly accessible, so a
  live core check reports "repository not found or not publicly accessible"
  and no update is staged. This is expected and handled honestly; it is not a
  coding failure and no version is invented. The reachable-but-no-stable-release
  path is covered by tests.

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
- **Update downloads are treated as untrusted.** Tarballs are fetched over TLS,
  extracted with path-traversal and symlink/hardlink escape checks, and
  fingerprints never include the `.jpnh-update.json` metadata file.
- **Proxy configuration is never hard-coded.** Proxies come from environment
  variables only; invalid proxy schemes fall back to a direct connection.

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
Checker bundle resolution, the `/checker/*` native tool API, API contracts, and
the update manager — including automatic adoption/baselining, backup/rollback
(rebuild after rollback), health checks, history fields, self-update
apply-on-restart (source + AppImage + deb), and the `/updates/runtime`,
`/updates/{id}/restart-apply`, and `/updates/pending-apply/clear` endpoints.

```bash
# Node tests for the pure-Node process managers, the self-updater, and the
# Updates view contract (event-driven, no periodic refresh)
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
