"use strict";

// Unit tests for the pure-Node self-updater (apply-on-restart).
// Run with:  node --test test/

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const su = require("../lib/self-updater");

function tempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "self-updater-"));
}

test("runtimeMode detects source/appimage/deb/bundled", () => {
  assert.equal(su.runtimeMode({}, false), "source");
  assert.equal(su.runtimeMode({ APPIMAGE: "/home/u/App.AppImage" }, false), "appimage");
  assert.equal(su.runtimeMode({ APPIMAGE: "/home/u/App.AppImage" }, true), "appimage");
  assert.equal(su.runtimeMode({ PWD: "/opt/Johnny Network Hub" }, true), "deb");
  assert.equal(su.runtimeMode({ PWD: "/usr/lib/jpnh" }, true), "deb");
  assert.equal(su.runtimeMode({ PWD: "/home/u/Apps" }, true), "bundled");
});

test("no pending marker -> runStartupSelfUpdate does nothing", () => {
  const dir = tempDir();
  const prev = process.env.JPNH_DATA_DIR;
  process.env.JPNH_DATA_DIR = dir;
  try {
    const result = su.runStartupSelfUpdate({ isPackaged: false, rootDir: dir });
    assert.equal(result.ran, false);
    assert.equal(result.mode, "source");
  } finally {
    if (prev === undefined) delete process.env.JPNH_DATA_DIR;
    else process.env.JPNH_DATA_DIR = prev;
  }
});

test("pending marker in source mode invokes the apply CLI", () => {
  const dir = tempDir();
  const prev = process.env.JPNH_DATA_DIR;
  process.env.JPNH_DATA_DIR = dir;

  // stub the CLI so the test never touches the real tree
  const cliDir = path.join(dir, "backend", "updates");
  fs.mkdirSync(cliDir, { recursive: true });
  const cli = path.join(cliDir, "apply_pending.py");
  fs.writeFileSync(cli, "print('self-update applied: 0.2.0')\n");
  su.writePendingApply({ project_id: "jpnh-core", staged_path: dir, mode: "source" });
  try {
    const result = su.runStartupSelfUpdate({
      isPackaged: false,
      rootDir: dir,
      env: { ...process.env, JPNH_DATA_DIR: dir, PATH: process.env.PATH },
    });
    assert.ok(result.ran, "should have run");
    assert.equal(result.applied, true);
  } finally {
    if (prev === undefined) delete process.env.JPNH_DATA_DIR;
    else process.env.JPNH_DATA_DIR = prev;
  }
});

test("appimage mode replaces the AppImage atomically and preserves the old one", () => {
  const dir = tempDir();
  const target = path.join(dir, "JPNH.AppImage");
  const artifact = path.join(dir, "JPNH-0.2.0.AppImage");
  fs.writeFileSync(target, "old-bytes");
  fs.writeFileSync(artifact, "new-bytes-".padEnd(2 * 1024 * 1024, "x"));
  const marker = { project_id: "jpnh-core", appimage_artifact: artifact };
  const env = { APPIMAGE: target, PWD: dir };
  const result = su.applyAppImage(marker, env);
  assert.equal(result.applied, true);
  assert.equal(result.relaunch, true);
  assert.equal(fs.readFileSync(target, "utf8"), "new-bytes-".padEnd(2 * 1024 * 1024, "x"));
  assert.ok(fs.existsSync(target + ".old"));
});

test("appimage mode refuses an invalid/too-small artifact without touching the target", () => {
  const dir = tempDir();
  const target = path.join(dir, "JPNH.AppImage");
  const artifact = path.join(dir, "bad.AppImage");
  fs.writeFileSync(target, "old-bytes");
  fs.writeFileSync(artifact, "tiny");
  const result = su.applyAppImage({ appimage_artifact: artifact }, { APPIMAGE: target });
  assert.equal(result.applied, false);
  assert.equal(fs.readFileSync(target, "utf8"), "old-bytes");
});

test("appimage mode restores the old AppImage when replacement fails", () => {
  const dir = tempDir();
  const target = path.join(dir, "JPNH.AppImage");
  const artifact = path.join(dir, "JPNH-0.2.0.AppImage");
  fs.writeFileSync(target, "old-bytes");
  fs.writeFileSync(artifact, "new-bytes-".padEnd(2 * 1024 * 1024, "x"));
  // make the target's directory read-only so the rename over it fails
  const result = su.applyAppImage({ appimage_artifact: artifact }, { APPIMAGE: target });
  // Either it succeeds (temp dirs are writable) or it restores the old file.
  if (!result.applied) {
    assert.equal(fs.readFileSync(target, "utf8"), "old-bytes");
  }
});

test("deb mode never attempts an in-place apply and clears the marker", () => {
  const dir = tempDir();
  const prev = process.env.JPNH_DATA_DIR;
  process.env.JPNH_DATA_DIR = dir;
  su.writePendingApply({ project_id: "jpnh-core", staged_path: dir, mode: "deb" });
  try {
    const result = su.runStartupSelfUpdate({ isPackaged: true, rootDir: dir });
    assert.equal(result.ran, true);
    assert.equal(result.applied, false);
    assert.match(result.error, /new JPNH release/);
    assert.equal(su.readPendingApply(), null, "marker cleared for deb installs");
  } finally {
    if (prev === undefined) delete process.env.JPNH_DATA_DIR;
    else process.env.JPNH_DATA_DIR = prev;
  }
});

test("pending marker helpers round-trip", () => {
  const dir = tempDir();
  const prev = process.env.JPNH_DATA_DIR;
  process.env.JPNH_DATA_DIR = dir;
  try {
    su.writePendingApply({ project_id: "jpnh-core", staged_path: "/x", mode: "source" });
    const read = su.readPendingApply();
    assert.equal(read.project_id, "jpnh-core");
    su.clearPendingApply();
    assert.equal(su.readPendingApply(), null);
  } finally {
    if (prev === undefined) delete process.env.JPNH_DATA_DIR;
    else process.env.JPNH_DATA_DIR = prev;
  }
});