"use strict";

const fs = require("fs");
const path = require("path");
const { app } = require("electron");

let history = [];
let dirty = false;
let saveTimer = null;

function historyPath() {
  return path.join(app.getPath("userData"), "browser-history.json");
}

function load() {
  try {
    const data = fs.readFileSync(historyPath(), "utf-8");
    history = JSON.parse(data);
  } catch (_) {
    history = [];
  }
}

function save() {
  try {
    fs.writeFileSync(historyPath(), JSON.stringify(history, null, 2));
    dirty = false;
  } catch (_) { /* non-fatal */ }
}

function scheduleSave() {
  if (dirty) return;
  dirty = true;
  saveTimer = setTimeout(() => {
    save();
    clearTimeout(saveTimer);
    saveTimer = null;
  }, 2000);
}

function add(url, title) {
  if (!url || url.startsWith("about:") || url.startsWith("chrome:") || url.startsWith("devtools:")) return;

  const existing = history.find((h) => h.url === url);
  if (existing) {
    existing.title = title || existing.title;
    existing.visits = (existing.visits || 1) + 1;
    existing.lastVisit = Date.now();
  } else {
    history.push({
      url,
      title: title || url,
      visits: 1,
      firstVisit: Date.now(),
      lastVisit: Date.now(),
    });
  }

  if (history.length > 5000) {
    history.sort((a, b) => b.lastVisit - a.lastVisit);
    history = history.slice(0, 5000);
  }

  scheduleSave();
}

function getAll() {
  return history.slice().sort((a, b) => b.lastVisit - a.lastVisit);
}

function search(query) {
  const q = query.toLowerCase();
  return history
    .filter(
      (h) =>
        (h.url && h.url.toLowerCase().includes(q)) ||
        (h.title && h.title.toLowerCase().includes(q))
    )
    .sort((a, b) => b.lastVisit - a.lastVisit)
    .slice(0, 100);
}

function clear() {
  history = [];
  save();
}

function clearRange(from, to) {
  history = history.filter((h) => h.lastVisit < from || h.lastVisit > to);
  save();
}

load();

module.exports = { add, getAll, search, clear, clearRange, save };
