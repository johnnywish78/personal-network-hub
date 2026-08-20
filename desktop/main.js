"use strict";

const { app, BrowserWindow, shell, ipcMain, dialog } = require("electron");
const path = require("path");
const fs = require("fs");

const bm = require("./lib/backend-manager");
const ncm = require("./lib/network-checker-manager");
const updater = require("./lib/self-updater");

// On Linux, Electron derives the window WM_CLASS from app.name. The packaged
// .desktop entry sets StartupWMClass=jpnh, so pin the name to match — otherwise
// Ubuntu Dock/GNOME can't associate the window with the launcher and shows a
// generic gear icon instead of the app icon.
if (process.platform === "linux") app.setName("jpnh");

const API_HOST = "127.0.0.1";
const BASE_PORT = 8765;
const MAX_PORT_OFFSET = 50;

// Development mode: run from the source tree (`npm start` / `./scripts/run.sh`).
// --dev forces development mode even when packaged.
const isDev = process.argv.includes("--dev") || !app.isPackaged;

let backend = null; // { child, port }
let mainWindow = null;
let logFile = null;
let networkChecker = null; // { child }

// ---- diagnostics ----------------------------------------------------------

function log(...parts) {
  const line = `[${new Date().toISOString()}] ${parts.join(" ")}`;
  if (isDev) console.log(line);
  try {
    if (!logFile) {
      const dir = app.getPath("userData");
      fs.mkdirSync(dir, { recursive: true });
      logFile = path.join(dir, "backend.log");
    }
    fs.appendFileSync(logFile, line + "\n");
  } catch (_) { /* never let logging break the app */ }
}

// ---- backend lifecycle ----------------------------------------------------

async function startBackend() {
  const rootDir = path.join(__dirname, "..");
  const resourcesPath = process.resourcesPath;

  log("starting backend (packaged=", app.isPackaged, ", dev=", isDev, ")");
  let prep;
  try {
    prep = await bm.prepareBackend({
      isPackaged: app.isPackaged,
      dev: isDev,
      rootDir,
      resourcesPath,
      host: API_HOST,
      basePort: BASE_PORT,
      maxOffset: MAX_PORT_OFFSET,
    });
  } catch (err) {
    log("backend preparation failed:", err.message);
    dialog.showErrorBox(
      "JPNH could not start",
      `The local backend could not be prepared.\n\n${err.message}`
    );
    app.exit(1);
    return null;
  }

  log("spawning backend on", prep.host + ":" + prep.port, "->", prep.command);
  const child = bm.spawnBackend(prep);
  backend = { child, port: prep.port };

  child.stdout.on("data", (d) => log("[backend]", d.toString().trim()));
  child.stderr.on("data", (d) => log("[backend:err]", d.toString().trim()));
  child.on("error", (err) => log("backend spawn error:", err.message));
  child.on("exit", (code, signal) => {
    log("backend exited code=", code, "signal=", signal);
    if (backend && backend.child === child) backend.child = null;
  });

  try {
    await bm.waitForReady({ host: API_HOST, port: prep.port, timeoutMs: 30000, log });
  } catch (err) {
    log("backend failed to become ready:", err.message);
    dialog.showErrorBox(
      "JPNH backend failed to start",
      `${err.message}\n\nSee the log for details.`
    );
    bm.killBackend(child);
    app.exit(1);
    return null;
  }

  log("backend ready on", prep.host + ":" + prep.port);
  return prep.port;
}

function stopBackend() {
  if (backend && backend.child) {
    log("stopping backend (pid", backend.child.pid, ")");
    bm.killBackend(backend.child);
    backend.child = null;
  }
}

// ---- bundled Network Checker lifecycle ------------------------------------

function networkCheckerCommand() {
  const prep = ncm.prepareNetworkChecker({
    isPackaged: app.isPackaged,
    dev: isDev,
    rootDir: path.join(__dirname, ".."),
    resourcesPath: process.resourcesPath,
  });
  if (!prep.installed) return null;
  return prep.command;
}

function launchNetworkChecker() {
  if (networkChecker && networkChecker.child) {
    return { ok: true, alreadyRunning: true };
  }
  const command = networkCheckerCommand();
  if (!command) {
    log("network-checker bundle not found");
    return { ok: false, error: "Network Checker bundle is not present" };
  }
  log("launching network-checker ->", command);
  const child = ncm.spawnNetworkChecker({ command });
  networkChecker = { child };
  child.stdout.on("data", (d) => log("[network-checker]", d.toString().trim()));
  child.stderr.on("data", (d) => log("[network-checker:err]", d.toString().trim()));
  child.on("error", (err) => log("network-checker spawn error:", err.message));
  child.on("exit", (code, signal) => {
    log("network-checker exited code=", code, "signal=", signal);
    if (networkChecker && networkChecker.child === child) networkChecker.child = null;
  });
  return { ok: true, pid: child.pid };
}

function stopNetworkChecker() {
  if (networkChecker && networkChecker.child) {
    log("stopping network-checker (pid", networkChecker.child.pid, ")");
    ncm.killNetworkChecker(networkChecker.child);
    networkChecker.child = null;
  }
}

// ---- window ---------------------------------------------------------------

function windowIconPath() {
  if (app.isPackaged) {
    const p = path.join(process.resourcesPath, "icons", "icon.png");
    return fs.existsSync(p) ? p : undefined;
  }
  const p = path.join(__dirname, "..", "assets", "icons", "icon.png");
  return fs.existsSync(p) ? p : undefined;
}

function createWindow() {
  const iconPath = windowIconPath();
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    minHeight: 640,
    backgroundColor: "#111418",
    title: "Johnny Personal Network Hub",
    icon: iconPath,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      webviewTag: true,
    },
  });

  mainWindow.setMenuBarVisibility(false);

  // On Linux the constructor icon can be dropped (especially under Wayland/
  // XWayland); setting it again on the window guarantees _NET_WM_ICON is set.
  if (iconPath) mainWindow.setIcon(iconPath);

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith("file://")) {
      event.preventDefault();
      if (url.startsWith("http://") || url.startsWith("https://")) shell.openExternal(url);
    }
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
}

// ---- IPC ------------------------------------------------------------------

ipcMain.handle("open-external", (_event, url) => {
  if (typeof url === "string" && (url.startsWith("http://") || url.startsWith("https://"))) {
    return shell.openExternal(url);
  }
  return { error: "invalid url" };
});

ipcMain.handle("backend-url", () => {
  const port = backend ? backend.port : BASE_PORT;
  return `http://${API_HOST}:${port}`;
});

ipcMain.handle("network-checker-launch", () => launchNetworkChecker());
ipcMain.handle("network-checker-stop", () => { stopNetworkChecker(); return { ok: true }; });
ipcMain.handle("network-checker-status", () => ({
  running: !!(networkChecker && networkChecker.child),
  installed: !!networkCheckerCommand(),
}));

ipcMain.handle("app-quit", () => {
  quitCleanly();
  return { ok: true };
});

// ---- app lifecycle --------------------------------------------------------

app.whenReady().then(async () => {
  // Apply a pending self-update (Restart & Update) before anything starts.
  const selfUpdate = updater.runStartupSelfUpdate({
    isPackaged: app.isPackaged,
    rootDir: path.join(__dirname, ".."),
  });
  if (selfUpdate.ran) {
    if (selfUpdate.applied) {
      log("self-update applied:", selfUpdate.detail || selfUpdate.mode);
    } else {
      log("self-update pending but not applied:", selfUpdate.error || "unknown");
    }
    if (selfUpdate.applied && selfUpdate.relaunch) {
      log("relaunching into the updated AppImage");
      app.relaunch();
      app.exit(0);
      return;
    }
  }

  await startBackend();
  if (app.isQuitting) return;
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

let quitting = false;
function quitCleanly() {
  if (quitting) return;
  quitting = true;
  stopBackend();
  stopNetworkChecker();
  app.quit();
}

app.on("window-all-closed", () => {
  stopBackend();
  stopNetworkChecker();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => { stopBackend(); stopNetworkChecker(); });
app.on("will-quit", () => { stopBackend(); stopNetworkChecker(); });
app.on("quit", () => {
  if (logFile) {
    try { fs.appendFileSync(logFile, "\n[JPNH] application exiting\n"); } catch (_) {}
  }
});

// If the desktop process receives a termination signal, clean up all children
// and exit. app.quit() alone can hang on Linux when the renderer/GPU services
// are mid-teardown, so we force a clean exit shortly after the graceful path.
for (const sig of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(sig, () => {
    quitCleanly();
    setTimeout(() => {
      try { app.exit(0); } catch (_) {}
    }, 800).unref();
  });
}