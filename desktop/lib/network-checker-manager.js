"use strict";

// Pure-Node child-process manager for the bundled Network Checker app.
//
// This module is deliberately free of any `electron` import so it can be unit
// tested with plain Node. All Electron-specific values (app.isPackaged,
// app.getAppPath(), process.resourcesPath) are passed in by the caller
// (main.js) via the options objects below.

const { spawn, spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

function platformDir(platform) {
  if (platform === "win32") return "win";
  if (platform === "darwin") return "mac";
  return "linux";
}

function exeName(platform) {
  return platformDir(platform) === "win" ? "rdnbenet.exe" : "rdnbenet";
}

// Resolve the bundled Network Checker executable.
// - packaged: <resourcesPath>/network-checker/<platform>/rdnbenet
// - dev:      <rootDir>/third_party/network-checker/build/<platform>/x64/release/bundle/rdnbenet
function resolveNetworkChecker({ isPackaged, dev, rootDir, resourcesPath }) {
  const dir = platformDir(process.platform);
  const exe = exeName(process.platform);
  if (isPackaged && !dev) {
    return path.join(resourcesPath, "network-checker", dir, exe);
  }
  return path.join(
    rootDir, "third_party", "network-checker", "build",
    dir, "x64", "release", "bundle", exe
  );
}

function isInstalled(command) {
  return typeof command === "string" && command.length > 0 && fs.existsSync(command);
}

// Spawn the bundled app. The Flutter bundle is self-contained, so the working
// directory is set to the bundle dir to keep lib/ and data/ resolvable.
function spawnNetworkChecker({ command }) {
  const opts = {
    cwd: path.dirname(command),
    env: { ...process.env },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  };
  if (process.platform !== "win32") opts.detached = true;
  return spawn(command, [], opts);
}

// Terminate the app (and its process tree, which may include an Xray child).
// Same strategy as the backend: SIGTERM to the process group with a SIGKILL
// safety net on POSIX, taskkill /T /F on Windows.
function killNetworkChecker(child, platform = process.platform) {
  if (!child || !child.pid) return;
  try {
    if (platform === "win32") {
      spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    } else {
      try {
        process.kill(-child.pid, "SIGTERM");
      } catch (_) {
        child.kill("SIGTERM");
      }
      setTimeout(() => {
        try {
          process.kill(-child.pid, "SIGKILL");
        } catch (_) {
          try {
            child.kill("SIGKILL");
          } catch (_) {}
        }
      }, 1500).unref();
    }
  } catch (_) {
    try {
      child.kill("SIGKILL");
    } catch (_) {}
  }
}

// Resolve + probe the bundle, returning what a launcher needs.
function prepareNetworkChecker({ isPackaged, dev, rootDir, resourcesPath }) {
  const command = resolveNetworkChecker({ isPackaged, dev, rootDir, resourcesPath });
  return { command, installed: isInstalled(command) };
}

module.exports = {
  platformDir,
  exeName,
  resolveNetworkChecker,
  isInstalled,
  spawnNetworkChecker,
  killNetworkChecker,
  prepareNetworkChecker,
};
