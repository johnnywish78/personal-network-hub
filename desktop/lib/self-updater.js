"use strict";

// Pure-Node self-updater for JPNH. Runs at application startup, BEFORE the
// backend is spawned, and consumes the pending-apply marker left by the Update
// Manager when the user chose "Restart & Update".
//
// Deliberately free of any `electron` import so it can be unit tested with
// plain Node (`node --test test/`). Electron-specific values are passed in via
// the options object.
//
// Modes:
//   * source (dev/`npm start`): the staged JPNH Core source tree is swapped
//     into the repository root by the backend's `apply_pending` CLI (which has
//     the full backup + health-check + rollback machinery).
//   * appimage: the marker records a downloaded AppImage artifact; when one is
//     present it is atomically replaced over the running AppImage (the old file
//     is preserved as <name>.old). The process then relaunches into the new
//     version.
//   * deb/bundled: resources are read-only; an in-place apply is impossible and
//     is never attempted. The marker is cleared and a clear message returned.

const { spawnSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const PENDING_FILE = "pending-apply.json";

function dataDir() {
  return process.env.JPNH_DATA_DIR || path.join(os.homedir(), ".jpnh");
}

function pendingApplyPath() {
  return path.join(dataDir(), PENDING_FILE);
}

function readPendingApply() {
  try {
    const text = fs.readFileSync(pendingApplyPath(), "utf-8");
    const data = JSON.parse(text);
    return data && typeof data === "object" ? data : null;
  } catch (_) {
    return null;
  }
}

function writePendingApply(payload) {
  fs.mkdirSync(dataDir(), { recursive: true });
  fs.writeFileSync(pendingApplyPath(), JSON.stringify(payload, null, 2));
}

function clearPendingApply() {
  try {
    fs.unlinkSync(pendingApplyPath());
  } catch (_) { /* already gone */ }
}

function runtimeMode(env, isPackaged) {
  if (env.APPIMAGE) return "appimage";
  if (!isPackaged) return "source";
  const cwd = env.PWD || "";
  if (cwd.startsWith("/opt") || cwd.startsWith("/usr")) return "deb";
  return "bundled";
}

// Find the project virtualenv python (source mode only).
function findPython(rootDir) {
  const candidates = [
    path.join(rootDir, ".venv", "bin", "python"),
    path.join(rootDir, ".venv", "Scripts", "python.exe"),
    path.join(rootDir, "backend", ".venv", "bin", "python"),
    "python3",
    "python",
  ];
  for (const c of candidates) {
    try {
      const r = spawnSync(c, ["-c", "import sys; print(sys.version_info[:2])"], { encoding: "utf8" });
      if (!r.error && r.status === 0 && r.stdout) return c;
    } catch (_) { /* try next */ }
  }
  return "python3";
}

function applySourceUpdate({ rootDir, env }) {
  const python = findPython(rootDir);
  const mod = path.join(rootDir, "backend", "updates", "apply_pending.py");
  const res = spawnSync(python, [mod], {
    cwd: rootDir,
    encoding: "utf8",
    env,
    timeout: 600000,
  });
  const output = (res.stdout || "") + (res.stderr || "");
  if (res.error || res.status !== 0) {
    return { applied: false, error: output.trim() || "self-update process failed" };
  }
  return { applied: true, detail: output.trim() };
}

// Atomically replace the running AppImage; the old file is preserved next to it.
function applyAppImage(marker, env) {
  const target = env.APPIMAGE;
  const artifact = marker.appimage_artifact;
  if (!target || !artifact) {
    return { applied: false, error: "AppImage path or downloaded artifact is missing" };
  }
  if (!fs.existsSync(target)) {
    return { applied: false, error: `running AppImage not found: ${target}` };
  }
  if (!fs.existsSync(artifact)) {
    return { applied: false, error: `downloaded artifact not found: ${artifact}` };
  }
  try {
    const stat = fs.statSync(artifact);
    if (!stat.isFile() || stat.size < 1024 * 1024) {
      return { applied: false, error: "downloaded artifact looks invalid (too small)" };
    }
    const oldPath = target + ".old";
    if (fs.existsSync(oldPath)) fs.unlinkSync(oldPath);
    fs.renameSync(target, oldPath);
    try {
      fs.renameSync(artifact, target);
    } catch (err) {
      fs.renameSync(oldPath, target); // restore the old version
      return { applied: false, error: `replacement failed, restored old version: ${err.message}` };
    }
    fs.chmodSync(target, stat.mode || 0o755);
    return { applied: true, relaunch: true, old: oldPath };
  } catch (err) {
    return { applied: false, error: err.message };
  }
}

// Public entry: run the pending self-update, if any. Returns a result object
// and never throws.
function runStartupSelfUpdate({ isPackaged = false, rootDir = process.cwd() } = {}) {
  const env = { ...process.env };
  const mode = runtimeMode(env, isPackaged);
  const marker = readPendingApply();
  if (!marker) return { ran: false, mode };

  if (mode === "appimage") {
    const result = applyAppImage(marker, env);
    if (result.applied) clearPendingApply();
    return { ran: true, mode, ...result };
  }

  if (mode === "source") {
    const result = applySourceUpdate({ rootDir, env });
    if (result.applied) clearPendingApply();
    return { ran: true, mode, ...result };
  }

  // deb/bundled: read-only resources; never attempt an in-place swap.
  clearPendingApply();
  return {
    ran: true,
    mode,
    applied: false,
    error: "Running from a packaged build; JPNH Core is updated by installing the new JPNH release.",
  };
}

module.exports = {
  runStartupSelfUpdate,
  applySourceUpdate,
  applyAppImage,
  readPendingApply,
  writePendingApply,
  clearPendingApply,
  runtimeMode,
  dataDir,
  pendingApplyPath,
};
