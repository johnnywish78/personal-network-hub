"use strict";

// Pure-Node backend process manager for JPNH.
//
// This module is deliberately free of any `electron` import so it can be unit
// tested with plain Node (`node --test test/`). All Electron-specific values
// (app.isPackaged, app.getAppPath(), process.resourcesPath) are passed in by
// the caller (main.js) via the options objects below.

const { spawn, spawnSync } = require("child_process");
const http = require("http");
const net = require("net");
const path = require("path");
const fs = require("fs");

const BACKEND_EXE = {
  win: "jpnh-backend.exe",
  linux: "jpnh-backend",
  mac: "jpnh-backend",
};

function platformDir(platform) {
  if (platform === "win32") return "win";
  if (platform === "darwin") return "mac";
  return "linux";
}

function exeName(platform) {
  return BACKEND_EXE[platformDir(platform)] || "jpnh-backend";
}

// Locate the project virtualenv Python (development mode only).
function findPython(rootDir) {
  const candidates = [
    path.join(rootDir, ".venv", "bin", "python"),
    path.join(rootDir, ".venv", "Scripts", "python.exe"),
    path.join(rootDir, "backend", ".venv", "bin", "python"),
    "python3",
    "python",
  ];
  for (const candidate of candidates) {
    if (candidate.includes(path.sep)) {
      if (fs.existsSync(candidate)) return candidate;
    } else {
      return candidate; // rely on PATH
    }
  }
  return "python3";
}

function resolveBackendExecutable({ isPackaged, dev, rootDir, resourcesPath }) {
  if (isPackaged && !dev) {
    return path.join(resourcesPath, "backend", platformDir(process.platform), exeName(process.platform));
  }
  return findPython(rootDir);
}

// Build the argv for the backend, based on dev vs packaged mode.
function buildCommand({ isPackaged, dev, rootDir, resourcesPath, host, port }) {
  if (isPackaged && !dev) {
    return {
      command: resolveBackendExecutable({ isPackaged, dev, rootDir, resourcesPath }),
      args: ["--host", host, "--port", String(port)],
      cwd: path.dirname(resolveBackendExecutable({ isPackaged, dev, rootDir, resourcesPath })),
      envExtra: {},
    };
  }
  return {
    command: findPython(rootDir),
    args: ["-m", "backend.main", "--host", host, "--port", String(port)],
    cwd: rootDir,
    envExtra: {},
  };
}

// Return a free TCP port on `host`, starting at `base` and scanning up to
// `base + maxOffset`. Falls back to any free ephemeral port.
function findFreePort({ base, host, maxOffset = 50 }) {
  const start = base || 0;
  const probe = (port) =>
    new Promise((resolve) => {
      const server = net.createServer();
      server.unref();
      server.on("error", () => resolve(null));
      server.listen({ host, port }, () => {
        const actual = server.address().port;
        server.close(() => resolve(actual));
      });
    });

  return (async () => {
    for (let p = start; p < start + (maxOffset || 1); p++) {
      const free = await probe(p);
      if (free !== null) return free;
    }
    const ephemeral = await probe(0);
    return ephemeral;
  })();
}

function isPortFree({ host, port }) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.once("error", () => resolve(false));
    server.listen({ host, port }, () => {
      server.close(() => resolve(true));
    });
  });
}

// Wait for the backend to answer GET /ping on host:port.
function waitForReady({ host, port, timeoutMs = 30000, log = () => {} }) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get({ host, port, path: "/ping", timeout: 1000 }, (res) => {
        res.resume();
        if (res.statusCode === 200) return resolve(true);
        retry();
      });
      req.on("error", retry);
      req.on("timeout", () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() > deadline) {
        return reject(new Error(`backend did not become ready on ${host}:${port} within ${timeoutMs}ms`));
      }
      setTimeout(attempt, 300);
    };
    attempt();
  });
}

// Spawn the backend child process.
// - POSIX: detached so the whole process group can be terminated on exit.
// - Windows: windowsHide so no console window flashes next to the GUI app.
function spawnBackend({ command, args, cwd, envExtra = {} }) {
  const opts = {
    cwd,
    env: { ...process.env, ...envExtra },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  };
  if (process.platform !== "win32") opts.detached = true;
  return spawn(command, args, opts);
}

// Terminate the backend child (and its process tree) synchronously.
// - Windows: taskkill /T /F kills the whole tree (PyInstaller onefile spawns
//   a real server in a child of the bootloader, so the tree must go).
// - POSIX: SIGTERM to the process group, with a SIGKILL safety net.
function killBackend(child, platform = process.platform) {
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

// Full preparation: resolve executable, pick a free port, build argv.
async function prepareBackend({ isPackaged, dev, rootDir, resourcesPath, host, basePort, maxOffset = 50 }) {
  const port = await findFreePort({ base: basePort, host, maxOffset });
  const cmd = buildCommand({ isPackaged, dev, rootDir, resourcesPath, host, port });
  return { ...cmd, port, host };
}

module.exports = {
  platformDir,
  exeName,
  findPython,
  resolveBackendExecutable,
  buildCommand,
  findFreePort,
  isPortFree,
  waitForReady,
  spawnBackend,
  killBackend,
  prepareBackend,
};