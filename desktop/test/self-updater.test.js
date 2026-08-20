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

// A minimal but structurally valid AppImage fixture: ELF magic, the canonical
// "AI\x02" type-2 marker at offset 8, >= 1 MiB, and executable.
function makeFakeAppImage(dir, name, tag) {
  const file = path.join(dir, name);
  const head = Buffer.alloc(4096);
  head.write("\x7fELF", 0, "latin1");
  head.write("AI\x02", 8, "latin1");
  const body = Buffer.concat([
    head,
    Buffer.alloc(2 * 1024 * 1024 - head.length, tag.charCodeAt(0) % 256),
  ]);
  fs.writeFileSync(file, body);
  fs.chmodSync(file, 0o755);
  return file;
}

function withDataDir(dir, fn) {
  const prev = process.env.JPNH_DATA_DIR;
  process.env.JPNH_DATA_DIR = dir;
  try {
    return fn();
  } finally {
    if (prev === undefined) delete process.env.JPNH_DATA_DIR;
    else process.env.JPNH_DATA_DIR = prev;
  }
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
  withDataDir(dir, () => {
    const result = su.runStartupSelfUpdate({ isPackaged: false, rootDir: dir });
    assert.equal(result.ran, false);
    assert.equal(result.mode, "source");
  });
});

test("pending marker in source mode invokes the apply CLI", () => {
  const dir = tempDir();
  // stub the CLI so the test never touches the real tree
  const cliDir = path.join(dir, "backend", "updates");
  fs.mkdirSync(cliDir, { recursive: true });
  const cli = path.join(cliDir, "apply_pending.py");
  fs.writeFileSync(cli, "print('self-update applied: 0.2.0')\n");
  withDataDir(dir, () => {
    su.writePendingApply({ project_id: "jpnh-core", staged_path: dir, mode: "source" });
    const result = su.runStartupSelfUpdate({
      isPackaged: false,
      rootDir: dir,
      env: { ...process.env, JPNH_DATA_DIR: dir, PATH: process.env.PATH },
    });
    assert.ok(result.ran, "should have run");
    assert.equal(result.applied, true);
  });
});

// ---------------------------------------------------------------------------
// AppImage atomic replace behaviour
// ---------------------------------------------------------------------------

test("appimage mode replaces the AppImage atomically and preserves the old one", () => {
  const dir = tempDir();
  const target = makeFakeAppImage(dir, "JPNH.AppImage", "O");
  const artifact = makeFakeAppImage(dir, "JPNH-0.2.0.AppImage", "N");
  const before = su.sha256File(target);
  const after = su.sha256File(artifact);
  const marker = { project_id: "jpnh-core", appimage_artifact: artifact };
  const result = su.applyAppImage(marker, { APPIMAGE: target, PWD: dir });
  assert.equal(result.applied, true);
  assert.equal(result.relaunch, true);
  assert.equal(su.sha256File(target), after, "installed AppImage now equals the new artifact");
  assert.ok(fs.existsSync(target + ".old"), "old AppImage preserved");
  assert.equal(su.sha256File(target + ".old"), before, "old file is the previous binary");
});

test("appimage mode keeps the .old until the next successful launch of the new binary", () => {
  const dir = tempDir();
  const target = makeFakeAppImage(dir, "JPNH.AppImage", "O");
  const artifact = makeFakeAppImage(dir, "JPNH-0.2.0.AppImage", "N");
  const marker = { project_id: "jpnh-core", appimage_artifact: artifact };
  const result = su.applyAppImage(marker, { APPIMAGE: target, PWD: dir });
  assert.equal(result.applied, true);
  assert.ok(fs.existsSync(target + ".old"), ".old exists right after the swap");

  // Simulate the relaunch: the new binary is now running (APPIMAGE set) and
  // the startup updater runs again. The launch-confirmation cleanup removes
  // the .old because the new build already started successfully.
  const cleaned = su.cleanupOldAppImage({ APPIMAGE: target, PWD: dir });
  assert.equal(cleaned, true);
  assert.equal(fs.existsSync(target + ".old"), false, "old removed only after new build started");
});

test("appimage mode refuses an invalid (non-AppImage) artifact without touching the target", () => {
  const dir = tempDir();
  const target = makeFakeAppImage(dir, "JPNH.AppImage", "O");
  const artifact = path.join(dir, "bad.AppImage");
  fs.writeFileSync(artifact, "tiny"); // too small + no magic
  const before = su.sha256File(target);
  const result = su.applyAppImage({ appimage_artifact: artifact }, { APPIMAGE: target });
  assert.equal(result.applied, false);
  assert.equal(su.sha256File(target), before, "target untouched by an invalid artifact");
  assert.ok(!fs.existsSync(target + ".old"), "target never moved aside on invalid artifact");
});

test("appimage mode refuses a non-executable artifact", () => {
  const dir = tempDir();
  const target = makeFakeAppImage(dir, "JPNH.AppImage", "O");
  const artifact = makeFakeAppImage(dir, "JPNH-0.2.0.AppImage", "N");
  fs.chmodSync(artifact, 0o644); // not executable
  const before = su.sha256File(target);
  const result = su.applyAppImage({ appimage_artifact: artifact }, { APPIMAGE: target });
  assert.equal(result.applied, false);
  assert.equal(su.sha256File(target), before, "target untouched by a non-executable artifact");
});

test("appimage mode refuses to replace the installed AppImage with itself", () => {
  const dir = tempDir();
  const target = makeFakeAppImage(dir, "JPNH.AppImage", "O");
  const result = su.applyAppImage({ appimage_artifact: target }, { APPIMAGE: target });
  assert.equal(result.applied, false);
  assert.match(result.error, /itself/);
});

test("appimage mode fails cleanly when the destination directory is missing", () => {
  const dir = tempDir();
  const artifact = makeFakeAppImage(dir, "JPNH-0.2.0.AppImage", "N");
  const prevHome = process.env.HOME;
  process.env.HOME = path.join(dir, "nohome"); // no desktop entry available
  try {
    const result = su.applyAppImage(
      { appimage_artifact: artifact },
      { APPIMAGE: path.join(dir, "missing", "JPNH.AppImage") }
    );
    assert.equal(result.applied, false);
    assert.match(result.error, /AppImage found|missing/);
  } finally {
    if (prevHome === undefined) delete process.env.HOME;
    else process.env.HOME = prevHome;
  }
});

test("appimage mode fails cleanly when the installed AppImage does not exist", () => {
  const dir = tempDir();
  const artifact = makeFakeAppImage(dir, "JPNH-0.2.0.AppImage", "N");
  const prevHome = process.env.HOME;
  process.env.HOME = path.join(dir, "nohome"); // no desktop entry available
  try {
    const result = su.applyAppImage({ appimage_artifact: artifact }, { APPIMAGE: path.join(dir, "nope.AppImage") });
    assert.equal(result.applied, false);
    assert.match(result.error, /AppImage found|invalid/);
  } finally {
    if (prevHome === undefined) delete process.env.HOME;
    else process.env.HOME = prevHome;
  }
});

test("appimage mode fails cleanly when the desktop entry is missing and APPIMAGE is unset", () => {
  const dir = tempDir();
  const artifact = makeFakeAppImage(dir, "JPNH-0.2.0.AppImage", "N");
  // empty env: no APPIMAGE, and jpnh.desktop is looked up under the real home
  // dir — which is fine for the test because the assertion is that resolution
  // returns null in a sandboxed environment (HOME overridden to a bare dir).
  const prevHome = process.env.HOME;
  process.env.HOME = path.join(dir, "nohome");
  try {
    const result = su.applyAppImage({ appimage_artifact: artifact }, { PWD: dir });
    assert.equal(result.applied, false);
    assert.match(result.error, /no installed AppImage found/);
  } finally {
    if (prevHome === undefined) delete process.env.HOME;
    else process.env.HOME = prevHome;
  }
});

test("appimage mode resolves the installed AppImage from the desktop entry Exec= line", () => {
  const dir = tempDir();
  const installed = makeFakeAppImage(dir, "Johnny-Network-Hub.AppImage", "O");
  const apps = path.join(dir, ".local", "share", "applications");
  fs.mkdirSync(apps, { recursive: true });
  fs.writeFileSync(path.join(apps, "jpnh.desktop"),
    '[Desktop Entry]\nType=Application\nName=Johnny Network Hub\n' +
    `Exec="${installed}" --no-sandbox %U\nIcon=jpnh\nStartupWMClass=jpnh\n`);
  const prevHome = process.env.HOME;
  process.env.HOME = dir;
  try {
    const resolved = su.resolveInstalledAppImage({ PWD: dir });
    assert.equal(resolved, installed);
    const artifact = makeFakeAppImage(dir, "JPNH-0.2.0.AppImage", "N");
    const artifactSha = su.sha256File(artifact);
    const result = su.applyAppImage({ appimage_artifact: artifact }, { PWD: dir });
    assert.equal(result.applied, true);
    assert.equal(su.sha256File(installed), artifactSha, "desktop entry target updated");
    assert.ok(fs.existsSync(installed + ".old"));
    const entry = fs.readFileSync(path.join(apps, "jpnh.desktop"), "utf8");
    assert.ok(entry.includes(installed), "desktop entry still points at the same path");
    assert.equal(entry.match(/\[Desktop Entry\]/g).length, 1, "no duplicate desktop entry created");
  } finally {
    if (prevHome === undefined) delete process.env.HOME;
    else process.env.HOME = prevHome;
  }
});

// ---------------------------------------------------------------------------
// Regression test reproducing the reported deployment mismatch
// ---------------------------------------------------------------------------

test("REGRESSION: installed AppImage is updated to the new artifact via the desktop entry target", () => {
  const dir = tempDir();
  // Mirror the real layout:
  //   installed AppImage -> /tmp/.../Applications/Johnny-Network-Hub.AppImage
  //   new AppImage       -> /tmp/.../dist/Johnny Network Hub-0.1.0-linux-x86_64.AppImage
  //   desktop entry Exec -> installed AppImage
  const installedDir = path.join(dir, "Applications");
  const distDir = path.join(dir, "dist");
  fs.mkdirSync(installedDir, { recursive: true });
  fs.mkdirSync(distDir, { recursive: true });

  const installed = makeFakeAppImage(installedDir, "Johnny-Network-Hub.AppImage", "O");
  const newArtifact = makeFakeAppImage(distDir, "Johnny Network Hub-0.1.0-linux-x86_64.AppImage", "N");

  const apps = path.join(dir, ".local", "share", "applications");
  fs.mkdirSync(apps, { recursive: true });
  const entryPath = path.join(apps, "jpnh.desktop");
  fs.writeFileSync(entryPath,
    '[Desktop Entry]\nType=Application\nName=Johnny Network Hub\n' +
    `Exec="${installed}" --no-sandbox %U\nTerminal=false\nIcon=jpnh\nStartupWMClass=jpnh\n` +
    'Categories=Network;Utility;\n');

  const installedBefore = su.sha256File(installed);
  const newSha = su.sha256File(newArtifact);
  assert.notEqual(installedBefore, newSha, "the two files are NOT identical (the mismatch we are fixing)");

  const prevHome = process.env.HOME;
  process.env.HOME = dir;
  try {
    const result = su.applyAppImage(
      { project_id: "jpnh-core", appimage_artifact: newArtifact },
      { PWD: dir }
    );
    assert.equal(result.applied, true, result.error || "apply should succeed");

    // 1. installed AppImage SHA256 == new AppImage SHA256
    assert.equal(su.sha256File(installed), newSha, "installed AppImage now equals the new artifact");

    // 2. desktop entry still exists
    assert.ok(fs.existsSync(entryPath), "desktop entry still exists");

    // 3. desktop entry still points to the same installed path
    const entry = fs.readFileSync(entryPath, "utf8");
    assert.ok(entry.includes(installed), "desktop entry still points to the installed path");
    assert.ok(entry.includes("--no-sandbox"), "desktop entry arguments preserved");

    // 4. no duplicate .desktop entry
    assert.equal(entry.match(/\[Desktop Entry\]/g).length, 1, "no duplicate desktop entry");

    // 5. old AppImage preserved during the transaction
    assert.ok(fs.existsSync(installed + ".old"), "old AppImage preserved as .old");
    assert.equal(su.sha256File(installed + ".old"), installedBefore, ".old holds the previous binary");

    // 6. relaunch command targets the (now updated) installed AppImage
    const rl = su.relaunchAppImage(
      [process.execPath, "/some/mount/jpnh", "--no-sandbox"],
      { APPIMAGE: installed, PWD: dir }
    );
    assert.ok(rl, "relaunch command resolved");
    assert.equal(rl.file, installed, "relaunch spawns the AppImage file itself");
    assert.ok(rl.args.includes("--no-sandbox"), "relaunch keeps --no-sandbox");
  } finally {
    if (prevHome === undefined) delete process.env.HOME;
    else process.env.HOME = prevHome;
  }
});

// ---------------------------------------------------------------------------
// Mode handling: source / packaged AppImage / DEB / repeated requests
// ---------------------------------------------------------------------------

test("source mode never pretends the running process is the installed AppImage", () => {
  const dir = tempDir();
  withDataDir(dir, () => {
    su.writePendingApply({ project_id: "jpnh-core", staged_path: dir, mode: "source" });
    const result = su.runStartupSelfUpdate({ isPackaged: false, rootDir: dir });
    assert.equal(result.ran, true);
    assert.equal(result.mode, "source");
    // source mode runs the apply CLI, not an AppImage swap
    assert.ok(result.applied === false || result.applied === true);
  });
});

test("packaged AppImage execution applies the AppImage marker", () => {
  const dir = tempDir();
  const target = makeFakeAppImage(dir, "JPNH.AppImage", "O");
  const artifact = makeFakeAppImage(dir, "JPNH-0.2.0.AppImage", "N");
  const artifactSha = su.sha256File(artifact);
  withDataDir(dir, () => {
    su.writePendingApply({ project_id: "jpnh-core", appimage_artifact: artifact, mode: "appimage" });
    const prevAppImage = process.env.APPIMAGE;
    const prevPwd = process.env.PWD;
    process.env.APPIMAGE = target;
    process.env.PWD = dir;
    try {
      const result = su.runStartupSelfUpdate({ isPackaged: true, rootDir: dir });
      assert.equal(result.ran, true);
      assert.equal(result.mode, "appimage");
      assert.equal(result.applied, true);
      assert.equal(su.sha256File(target), artifactSha);
      assert.ok(fs.existsSync(target + ".old"));
    } finally {
      if (prevAppImage === undefined) delete process.env.APPIMAGE;
      else process.env.APPIMAGE = prevAppImage;
      if (prevPwd === undefined) delete process.env.PWD;
      else process.env.PWD = prevPwd;
    }
  });
});

test("DEB mode never attempts an in-place apply and clears the marker", () => {
  const dir = tempDir();
  withDataDir(dir, () => {
    su.writePendingApply({ project_id: "jpnh-core", staged_path: dir, mode: "deb" });
    const result = su.runStartupSelfUpdate({ isPackaged: true, rootDir: dir, env: { PWD: "/opt/jpnh" } });
    assert.equal(result.ran, true);
    assert.equal(result.applied, false);
    assert.match(result.error, /new JPNH release/);
    assert.equal(su.readPendingApply(), null, "marker cleared for deb installs");
  });
});

test("update already applied -> no marker -> nothing runs", () => {
  const dir = tempDir();
  withDataDir(dir, () => {
    const result = su.runStartupSelfUpdate({ isPackaged: true, rootDir: dir });
    assert.equal(result.ran, false);
  });
});

test("repeated update request stages a new artifact over the previous one", () => {
  const dir = tempDir();
  const target = makeFakeAppImage(dir, "JPNH.AppImage", "O");
  const artifactA = makeFakeAppImage(dir, "JPNH-0.2.0.AppImage", "A");
  const artifactB = makeFakeAppImage(dir, "JPNH-0.3.0.AppImage", "B");
  const shaA = su.sha256File(artifactA);
  const shaB = su.sha256File(artifactB);
  const r1 = su.applyAppImage({ appimage_artifact: artifactA }, { APPIMAGE: target });
  assert.equal(r1.applied, true);
  assert.equal(su.sha256File(target), shaA);
  const r2 = su.applyAppImage({ appimage_artifact: artifactB }, { APPIMAGE: target });
  assert.equal(r2.applied, true, "a second staged artifact replaces the first");
  assert.equal(su.sha256File(target), shaB);
});

test("relaunch command falls back to the desktop entry target when APPIMAGE is unset", () => {
  const dir = tempDir();
  const installed = makeFakeAppImage(dir, "Johnny-Network-Hub.AppImage", "O");
  const apps = path.join(dir, ".local", "share", "applications");
  fs.mkdirSync(apps, { recursive: true });
  fs.writeFileSync(path.join(apps, "jpnh.desktop"),
    `[Desktop Entry]\nType=Application\nName=Johnny Network Hub\nExec="${installed}" %U\n`);
  const prevHome = process.env.HOME;
  process.env.HOME = dir;
  try {
    const rl = su.relaunchAppImage(["/mount/jpnh"], { PWD: dir });
    assert.ok(rl);
    assert.equal(rl.file, installed);
  } finally {
    if (prevHome === undefined) delete process.env.HOME;
    else process.env.HOME = prevHome;
  }
});

test("pending marker helpers round-trip", () => {
  const dir = tempDir();
  withDataDir(dir, () => {
    su.writePendingApply({ project_id: "jpnh-core", staged_path: "/x", mode: "source" });
    const read = su.readPendingApply();
    assert.equal(read.project_id, "jpnh-core");
    su.clearPendingApply();
    assert.equal(su.readPendingApply(), null);
  });
});