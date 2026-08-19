"use strict";

// Build the bundled Network Checker (upstream Flutter app) into resources.
//
//   node build/scripts/build-network-checker.mjs linux   -> resources/network-checker/linux/
//
// This runs `flutter build linux --release` in third_party/network-checker and
// copies the self-contained bundle (rdnbenet + lib/ + data/) into resources.
// The bundle is an UNMODIFIED build of the upstream mirarr-app/network-checker.

import { spawnSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const desktopDir = path.resolve(__dirname, "..", "..");
const rootDir = path.resolve(desktopDir, "..");

const requested = process.argv[2];
const platform = requested || (process.platform === "win32" ? "win" : "linux");

if (!["linux", "win"].includes(platform)) {
  console.error(`[build-network-checker] unknown target "${requested}" (expected linux or win)`);
  process.exit(1);
}

// Flutter is not cross-compilable for Windows on Linux.
if (platform === "win" && process.platform !== "win32") {
  console.error("[build-network-checker] Flutter cannot cross-compile a Windows app on Linux.");
  console.error("[build-network-checker] Run `flutter build windows --release` on a Windows machine.");
  process.exit(1);
}

const flutter = process.env.FLUTTER_BIN || "flutter";
const appDir = path.join(rootDir, "third_party", "network-checker");
if (!fs.existsSync(path.join(appDir, "pubspec.yaml"))) {
  console.error(`[build-network-checker] vendored app not found: ${appDir}`);
  process.exit(1);
}

console.log(`[build-network-checker] flutter build ${platform} --release ...`);
const build = spawnSync(flutter, ["build", platform === "win" ? "windows" : "linux", "--release"], {
  cwd: appDir,
  stdio: "inherit",
});
if (build.error) {
  console.error("[build-network-checker] failed to run flutter:", build.error.message);
  process.exit(1);
}
if (build.status !== 0) process.exit(build.status ?? 1);

let bundleDir;
if (platform === "win") {
  bundleDir = path.join(appDir, "build", "windows", "x64", "runner", "Release");
} else {
  bundleDir = path.join(appDir, "build", "linux", "x64", "release", "bundle");
}
if (!fs.existsSync(bundleDir)) {
  console.error(`[build-network-checker] expected bundle not found: ${bundleDir}`);
  process.exit(1);
}

const outDir = path.join(rootDir, "resources", "network-checker", platform);
fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });
fs.cpSync(bundleDir, outDir, { recursive: true });

const exe = platform === "win" ? "rdnbenet.exe" : "rdnbenet";
fs.chmodSync(path.join(outDir, exe), 0o755);
console.log(`[build-network-checker] OK: ${outDir}`);