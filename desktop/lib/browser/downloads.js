"use strict";

const path = require("path");
const { app, dialog } = require("electron");

let downloads = [];
let nextId = 1;
let mainWindowRef = null;

function init(mainWindow) {
  mainWindowRef = mainWindow;
  const session = mainWindow.webContents.session;

  session.on("will-download", (event, item) => {
    const id = nextId++;
    const defaultName = item.getFilename();
    const savePath = path.join(app.getPath("downloads"), defaultName);

    item.setSavePath(savePath);

    const info = {
      id,
      filename: defaultName,
      url: item.getURL(),
      totalBytes: item.getTotalBytes(),
      receivedBytes: 0,
      state: "progressing",
      savePath,
      startTime: Date.now(),
    };
    downloads.push(info);
    notify("download-started", info);

    item.on("updated", (event, state) => {
      if (state === "progressing") {
        info.receivedBytes = item.getReceivedBytes();
        info.totalBytes = item.getTotalBytes();
        notify("download-progress", {
          id: info.id,
          receivedBytes: info.receivedBytes,
          totalBytes: info.totalBytes,
          progress: info.totalBytes > 0 ? info.receivedBytes / info.totalBytes : 0,
        });
      }
    });

    item.once("done", (event, state) => {
      info.state = state;
      info.endTime = Date.now();
      notify("download-complete", {
        id: info.id,
        state,
        filename: info.filename,
        savePath: info.savePath,
      });
    });
  });
}

function notify(channel, data) {
  if (mainWindowRef && !mainWindowRef.isDestroyed()) {
    mainWindowRef.webContents.send(channel, data);
  }
}

function getAll() {
  return downloads.map((d) => ({
    id: d.id,
    filename: d.filename,
    url: d.url,
    totalBytes: d.totalBytes,
    receivedBytes: d.receivedBytes,
    state: d.state,
    savePath: d.savePath,
    progress: d.totalBytes > 0 ? d.receivedBytes / d.totalBytes : 0,
  }));
}

function cancel(id) {
  const d = downloads.find((d) => d.id === id);
  if (d) d.state = "cancelled";
}

function remove(id) {
  downloads = downloads.filter((d) => d.id !== id);
}

function clear() {
  downloads = [];
}

module.exports = { init, getAll, cancel, remove, clear };
