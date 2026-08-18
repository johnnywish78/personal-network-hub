"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jpnh", {
  // Open an external URL in the system browser.
  openExternal: (url) => ipcRenderer.invoke("open-external", url),
  // Base URL of the local backend.
  backendUrl: () => ipcRenderer.invoke("backend-url"),
  // Bundled Network Checker app (child-process lifecycle managed by main).
  networkChecker: {
    launch: () => ipcRenderer.invoke("network-checker-launch"),
    stop: () => ipcRenderer.invoke("network-checker-stop"),
    status: () => ipcRenderer.invoke("network-checker-status"),
  },
});
