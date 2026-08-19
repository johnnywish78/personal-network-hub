"use strict";

// Build the JPNH backend into a standalone executable with PyInstaller.
//
//   node build/scripts/build-backend.mjs linux   -> resources/backend/linux/jpnh-backend
//   node build/scripts/build-backend.mjs win     -> resources/backend/win/jpnh-backend.exe
//
// PyInstaller is NOT cross-compilable: the win target must be built on a
// Windows machine. This script refuses to silently produce a broken artifact.

import { spawnSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const desktopDir = path.resolve(__dirname, "..", "..");
const rootDir = path.resolve(desktopDir, "..");

const requested = process.argv[2];
const platform = requested || (process.platform === "win32" ? "win" : "linux");
const isWin = platform === "win";

if (requested && !["linux", "win"].includes(requested)) {
  console.error(`[build-backend] unknown target "${requested}" (expected linux or win)`);
  process.exit(1);
}

if (isWin && process.platform !== "win32") {
  console.error("[build-backend] PyInstaller cannot cross-compile a Windows executable on Linux.");
  console.error("[build-backend] Run `npm run build:win` on a Windows machine with Python 3 installed.");
  process.exit(1);
}

const python = isWin
  ? path.join(rootDir, ".venv", "Scripts", "python.exe")
  : path.join(rootDir, ".venv", "bin", "python");

if (!fs.existsSync(python)) {
  console.error(`[build-backend] Python virtualenv not found: ${python}`);
  console.error("[build-backend] Create it first with `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.");
  process.exit(1);
}

const name = "jpnh-backend";
const outDir = path.join(rootDir, "resources", "backend", platform);
const workDir = path.join(rootDir, "build", "pyinstaller");
const sep = isWin ? ";" : ":"; // PyInstaller --add-data separator
const addData = `${path.join(rootDir, "VERSION")}${sep}.`;
const entry = path.join(desktopDir, "build", "backend_entry.py");

fs.mkdirSync(outDir, { recursive: true });
fs.mkdirSync(workDir, { recursive: true });

const args = [
  "-m", "PyInstaller",
  "--noconfirm", "--clean",
  "--onefile",
  "--name", name,
  "--distpath", outDir,
  "--workpath", path.join(workDir, `work-${platform}`),
  "--specpath", workDir,
  "--add-data", addData,
  entry,
];

console.log(`[build-backend] PyInstaller (${platform})...`);
const res = spawnSync(python, args, { cwd: rootDir, stdio: "inherit" });
if (res.error) {
  console.error("[build-backend] failed to run PyInstaller:", res.error.message);
  process.exit(1);
}
if (res.status !== 0) process.exit(res.status ?? 1);

const exe = path.join(outDir, isWin ? `${name}.exe` : name);
console.log(`[build-backend] OK: ${exe}`);