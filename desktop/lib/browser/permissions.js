"use strict";

let mainWindowRef = null;
let pendingCallbacks = new Map();

function setup(mainWindow) {
  mainWindowRef = mainWindow;
  const session = mainWindow.webContents.session;

  session.setPermissionRequestHandler((webContents, permission, callback) => {
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    pendingCallbacks.set(id, callback);

    mainWindow.webContents.send("permission-request", {
      id,
      permission,
      requestingUrl: webContents.getURL(),
    });

    setTimeout(() => {
      if (pendingCallbacks.has(id)) {
        pendingCallbacks.get(id)(false);
        pendingCallbacks.delete(id);
      }
    }, 30000);
  });

  session.setPermissionCheckHandler((webContents, permission, requestingOrigin) => {
    return true;
  });
}

function respond(id, granted) {
  const cb = pendingCallbacks.get(id);
  if (cb) {
    cb(granted);
    pendingCallbacks.delete(id);
  }
}

function getPermissionLabel(permission) {
  const labels = {
    camera: "Camera",
    microphone: "Microphone",
    geolocation: "Location",
    notifications: "Notifications",
    "clipboard-read": "Clipboard Read",
    "clipboard-sanitized-write": "Clipboard Write",
    midi: "MIDI",
    "display-capture": "Screen Capture",
    fullscreen: "Fullscreen",
    pointerLock: "Pointer Lock",
    mediaKeySystem: "Media Key System",
    sensors: "Sensors",
    hiddenElements: "Hidden Elements",
    idleDetection: "Idle Detection",
    "serial-port": "Serial Port",
    "usb-device": "USB Device",
    "bluetooth-device": "Bluetooth Device",
    "hid-device": "HID Device",
    "window-management": "Window Management",
  };
  return labels[permission] || permission;
}

module.exports = { setup, respond, getPermissionLabel };
