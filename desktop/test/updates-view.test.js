"use strict";

// Requirement 14: the Updates view must be event-driven — no periodic refresh,
// no "seconds counter" driving a full re-render every second.

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const updatesSrc = fs.readFileSync(path.join(__dirname, "..", "renderer", "views", "updates.js"), "utf8");

test("updates view contains no periodic refresh mechanism", () => {
  assert.match(updatesSrc, /window\.Views\.updates/, "should define the view");
  assert.doesNotMatch(updatesSrc, /setInterval/, "must not use setInterval");
  assert.doesNotMatch(updatesSrc, /requestAnimationFrame/, "must not use rAF polling");
});

test("updates view exposes the event-driven flow", () => {
  assert.match(updatesSrc, /addEventListener\("click"/, "actions are event-driven");
  assert.match(updatesSrc, /Restart & Update/, "core self-update flow present");
  assert.match(updatesSrc, /Download & Stage/, "core stage flow present");
  assert.match(updatesSrc, /Update All/, "update-all present");
  assert.match(updatesSrc, /Check for Updates/, "check flow present");
});

test("updates view exposes the installed-AppImage self-update flow", () => {
  assert.match(updatesSrc, /Download AppImage/, "AppImage download action present");
  assert.match(updatesSrc, /Restart & Apply/, "AppImage apply action present");
  assert.match(updatesSrc, /apply-appimage/, "calls the apply-appimage endpoint");
  assert.match(updatesSrc, /stage-appimage/, "calls the stage-appimage endpoint");
  assert.match(updatesSrc, /installed AppImage:/, "shows the installed AppImage path");
});

test("updates view shows honest progress without fake percentages", () => {
  assert.match(updatesSrc, /spinner/, "indeterminate spinner present");
  assert.doesNotMatch(updatesSrc, /\d+\s*%/, "no fake percentage labels");
});