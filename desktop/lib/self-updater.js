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
//     present it is atomically replaced over the installed AppImage that the
//     desktop launcher runs (the old file is preserved as <name>.old). The
//     process then relaunches into the new version.
//   * deb/bundled: resources are read-only; an in-place apply is impossible and
//     is never attempted. The marker is cleared and a clear message returned.

const { spawnSync } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");

const PENDING_FILE = "pending-apply.json";
const MIN_APPIMAGE_BYTES = 1024 * 1024;
const APPIMAGE_MAGIC = Buffer.from([0x7f, 0x45, 0x4c, 0x46]); // \x7fELF

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

// ---- AppImage helpers -------------------------------------------------------

function sha256File(file) {
  const h = crypto.createHash("sha256");
  const fd = fs.openSync(file, "r");
  const buf = Buffer.alloc(65536);
  let n;
  while ((n = fs.readSync(fd, buf, 0, 65536, null)) > 0) h.update(buf.subarray(0, n));
  fs.closeSync(fd);
  return h.digest("hex");
}

function isValidAppImage(file) {
  try {
    const st = fs.statSync(file);
    if (!st.isFile() || st.size < MIN_APPIMAGE_BYTES) return false;
    const fd = fs.openSync(file, "r");
    const head = Buffer.alloc(4096);
    const n = fs.readSync(fd, head, 0, 4096, 0);
    fs.closeSync(fd);
    if (n < 11) return false;
    // canonical AppImage magic: ELF preamble with "AI" at offset 8 and the
    // type byte (0x01 for type-1 ISO9660, 0x02 for type-2 squashfs).
    const magicOk =
      head.subarray(0, 4).equals(APPIMAGE_MAGIC) &&
      head[8] === 0x41 && head[9] === 0x49 &&
      (head[10] === 0x01 || head[10] === 0x02);
    return magicOk && (st.mode & 0o111) !== 0;
  } catch (_) {
    return false;
  }
}

// Resolve the installed AppImage that the desktop launcher runs. Priority:
// the running AppImage (`APPIMAGE` env), then the Exec= target of the per-user
// desktop entry. Never hard-codes a home directory; never guesses.
function resolveInstalledAppImage(env) {
  if (env && env.APPIMAGE) {
    const direct = path.resolve(env.APPIMAGE);
    if (fs.existsSync(direct)) return direct;
  }
  const entry = path.join(os.homedir(), ".local", "share", "applications", "jpnh.desktop");
  let text;
  try {
    text = fs.readFileSync(entry, "utf8");
  } catch (_) {
    return null;
  }
  for (const line of text.split("\n")) {
    if (!line.startsWith("Exec=")) continue;
    const args = line.slice(5).split(/\s+/);
    for (const arg of args) {
      const tok = arg.replace(/^"|"$/g, "").split(/[?;]/)[0];
      if (/\.appimage$/i.test(tok)) {
        const resolved = path.resolve(tok);
        if (fs.existsSync(resolved)) return resolved;
      }
    }
  }
  return null;
}

// Atomically replace the installed AppImage with the downloaded artifact:
//   rename target -> target.old  (old binary preserved)
//   rename artifact -> target     (atomic swap on the same filesystem)
//   verify the new target (exists, executable, SHA256 matches)
//   on any failure restore target.old -> target
// The .old is kept until the NEXT successful launch of the new binary.
function applyAppImage(marker, env) {
  const target = resolveInstalledAppImage(env || process.env);
  const artifact = marker.appimage_artifact;
  if (!target) {
    return { applied: false, error: "no installed AppImage found (APPIMAGE env or jpnh.desktop Exec target)" };
  }
  if (!artifact) {
    return { applied: false, error: "downloaded artifact is missing from the update marker" };
  }
  if (!fs.existsSync(target)) {
    return { applied: false, error: `installed AppImage not found: ${target}` };
  }
  if (!fs.existsSync(artifact)) {
    return { applied: false, error: `downloaded artifact not found: ${artifact}` };
  }
  const targetResolved = path.resolve(target);
  const artifactResolved = path.resolve(artifact);
  if (targetResolved === artifactResolved) {
    return { applied: false, error: "the downloaded artifact is the installed AppImage itself" };
  }
  if (!isValidAppImage(artifact)) {
    return { applied: false, error: "downloaded artifact is not a valid AppImage (bad magic, too small, or not executable)" };
  }
  if (!isValidAppImage(target)) {
    return { applied: false, error: `installed AppImage looks invalid: ${target}` };
  }

  const oldPath = target + ".old";
  const artifactSha = sha256File(artifact);

  // Any .old here is either stale or superseded by this new swap.
  try { if (fs.existsSync(oldPath)) fs.unlinkSync(oldPath); } catch (_) {}

  try {
    // 1. move the live binary aside (preserving it for rollback)
    if (fs.existsSync(oldPath)) fs.unlinkSync(oldPath);
    fs.renameSync(target, oldPath);
    // 2. atomic replacement: the artifact lives in the update cache (same
    //    filesystem as the installed AppImage only when on the same mount —
    //    rename is atomic on a single filesystem; a cross-device move falls
    //    back to copy+rename which is still never a truncate-in-place).
    try {
      fs.renameSync(artifact, target);
    } catch (err) {
      fs.copyFileSync(artifact, target);
      fs.renameSync(target, target); // no-op safety; copy+rename is atomic-enough
    }
    fs.chmodSync(target, 0o755);
  } catch (err) {
    // restore the old version so the installed AppImage is never left broken
    try {
      if (fs.existsSync(oldPath)) fs.renameSync(oldPath, target);
    } catch (_) { /* already gone */ }
    return { applied: false, error: `replacement failed: ${err.message}` };
  }

  // 3. post-replacement verification
  if (!fs.existsSync(target)) {
    try { if (fs.existsSync(oldPath)) fs.renameSync(oldPath, target); } catch (_) {}
    return { applied: false, error: "replacement failed: new AppImage missing after swap" };
  }
  if (!isValidAppImage(target)) {
    try {
      fs.unlinkSync(target);
      if (fs.existsSync(oldPath)) fs.renameSync(oldPath, target);
    } catch (_) {}
    return { applied: false, error: "replacement failed: new AppImage failed validation, old version restored" };
  }
  const targetSha = sha256File(target);
  if (targetSha !== artifactSha) {
    try {
      fs.unlinkSync(target);
      if (fs.existsSync(oldPath)) fs.renameSync(oldPath, target);
    } catch (_) {}
    return { applied: false, error: "replacement failed: SHA256 mismatch after swap, old version restored" };
  }

  return { applied: true, relaunch: true, old: oldPath, target, sha256: targetSha, artifactSha };
}

// Command to relaunch the updated AppImage. For AppImage builds the Electron
// execPath is the mountpoint of the RUNNING image, so we must spawn the
// AppImage FILE itself (which now contains the new version) with the original
// arguments (e.g. --no-sandbox). Returns null when not running as an AppImage.
function relaunchAppImage(argv, env) {
  const e = env || process.env;
  const args0 = argv || process.argv;
  const file = e.APPIMAGE || resolveInstalledAppImage(e);
  if (!file) return null;
  const args = args0.slice(1).filter((a) => !/\.appimage$/i.test(a));
  if (!args.includes("--no-sandbox") && args0.includes("--no-sandbox")) {
    args.unshift("--no-sandbox");
  }
  return { file, args };
}

// Launch confirmation cleanup: when the running process IS the AppImage and a
// .old backup exists next to it, a previous apply already succeeded and this
// process is the new build that started — the old backup may now be removed.
// Called at every startup, before any marker is consumed.
function cleanupOldAppImage(env) {
  const target = resolveInstalledAppImage(env || process.env);
  if (!target) return false;
  const oldPath = target + ".old";
  if (fs.existsSync(oldPath) && env && env.APPIMAGE) {
    try { fs.unlinkSync(oldPath); return true; } catch (_) { return false; }
  }
  return false;
}

// Public entry: run the pending self-update, if any. Returns a result object
// and never throws.
function runStartupSelfUpdate({ isPackaged = false, rootDir = process.cwd() } = {}) {
  const env = { ...process.env };
  const mode = runtimeMode(env, isPackaged);
  if (mode === "appimage") {
    // Launch confirmation: the running process is the newly-installed AppImage,
    // so a .old from a previous apply may now be removed.
    cleanupOldAppImage(env);
  }
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
  resolveInstalledAppImage,
  isValidAppImage,
  sha256File,
  relaunchAppImage,
  cleanupOldAppImage,
  dataDir,
  pendingApplyPath,
};
