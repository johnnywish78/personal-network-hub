"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jpnh", {
  // Open an external URL in the system browser.
  openExternal: (url) => ipcRenderer.invoke("open-external", url),
  openChrome: (url) => ipcRenderer.invoke("open-chrome", url),
  // Base URL of the local backend.
  backendUrl: () => ipcRenderer.invoke("backend-url"),
  // Bundled Network Checker app (child-process lifecycle managed by main).
  networkChecker: {
    launch: () => ipcRenderer.invoke("network-checker-launch"),
    stop: () => ipcRenderer.invoke("network-checker-stop"),
    status: () => ipcRenderer.invoke("network-checker-status"),
  },
  // Quit the app (used after requesting a Restart & Update so the next launch
  // applies the staged JPNH Core update).
  quit: () => ipcRenderer.invoke("app-quit"),

  // Browser features
  browser: {
    showContextMenu: (options) => ipcRenderer.invoke("show-context-menu", options),
    download: (url) => ipcRenderer.invoke("download-url", { url }),
    getDownloads: () => ipcRenderer.invoke("get-downloads"),
    print: () => ipcRenderer.invoke("print-page"),
    exportPdf: () => ipcRenderer.invoke("export-pdf"),
    clearData: (types) => ipcRenderer.invoke("clear-browser-data", { types }),
    getHistory: (query) => ipcRenderer.invoke("get-history", { query }),
    addHistory: (url, title) => ipcRenderer.invoke("add-history", { url, title }),
    clearHistory: () => ipcRenderer.invoke("clear-history"),
    respondPermission: (id, granted) => ipcRenderer.invoke("respond-permission", { id, granted }),
  },

  // Event listeners for browser
  onDownloadStarted: (cb) => ipcRenderer.on("download-started", (_, data) => cb(data)),
  onDownloadProgress: (cb) => ipcRenderer.on("download-progress", (_, data) => cb(data)),
  onDownloadComplete: (cb) => ipcRenderer.on("download-complete", (_, data) => cb(data)),
  onPermissionRequest: (cb) => ipcRenderer.on("permission-request", (_, data) => cb(data)),
  onContextMenuAction: (cb) => ipcRenderer.on("context-menu-action", (_, data) => cb(data)),
  onBrowserOpenInTab: (cb) => ipcRenderer.on("browser-open-in-tab", (_, data) => cb(data)),
});
