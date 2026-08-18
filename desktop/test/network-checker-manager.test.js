"use strict";

// Unit tests for the pure-Node Network Checker process manager.
// Run with:  node --test test/

const test = require("node:test");
const assert = require("node:assert");
const path = require("node:path");
const { spawn } = require("node:child_process");

const ncm = require("../lib/network-checker-manager");

test("platformDir maps win32/linux/darwin", () => {
  assert.equal(ncm.platformDir("win32"), "win");
  assert.equal(ncm.platformDir("linux"), "linux");
  assert.equal(ncm.platformDir("darwin"), "mac");
});

test("exeName returns .exe on windows", () => {
  assert.equal(ncm.exeName("win32"), "rdnbenet.exe");
  assert.equal(ncm.exeName("linux"), "rdnbenet");
});

test("resolveNetworkChecker uses resourcesPath in packaged mode", () => {
  const p = ncm.resolveNetworkChecker({
    isPackaged: true,
    dev: false,
    rootDir: "/project",
    resourcesPath: "/opt/JPNH/resources",
  });
  const expected = process.platform === "win32"
    ? path.join("/opt/JPNH/resources", "network-checker", "win", "rdnbenet.exe")
    : path.join("/opt/JPNH/resources", "network-checker", "linux", "rdnbenet");
  assert.equal(p, expected);
});

test("resolveNetworkChecker uses third_party bundle in dev mode", () => {
  const p = ncm.resolveNetworkChecker({
    isPackaged: false,
    dev: false,
    rootDir: "/project",
    resourcesPath: "/x",
  });
  const expected = process.platform === "win32"
    ? path.join("/project", "third_party", "network-checker", "build", "win", "x64", "release", "bundle", "rdnbenet.exe")
    : path.join("/project", "third_party", "network-checker", "build", "linux", "x64", "release", "bundle", "rdnbenet");
  assert.equal(p, expected);
});

test("isInstalled only reports real files", () => {
  assert.equal(ncm.isInstalled("/definitely/not/here/rdnbenet"), false);
  assert.equal(ncm.isInstalled(""), false);
});

test("prepareNetworkChecker reports installed for a real bundle", () => {
  const bundle = path.join(__dirname, "..", "..", "resources", "network-checker", "linux", "rdnbenet");
  const prep = ncm.prepareNetworkChecker({
    isPackaged: true,
    dev: false,
    rootDir: "/project",
    resourcesPath: path.join(__dirname, "..", "..", "resources"),
  });
  if (process.platform === "linux" && require("node:fs").existsSync(bundle)) {
    assert.equal(prep.installed, true);
    assert.equal(prep.command, bundle);
  } else {
    assert.equal(prep.installed, false);
  }
});

test("killNetworkChecker terminates a spawned child process group", async () => {
  const child = spawn(process.execPath, ["-e", "setInterval(()=>{},1000)"], {
    stdio: "ignore",
    detached: process.platform !== "win32",
    windowsHide: true,
  });
  ncm.killNetworkChecker(child, process.platform);
  const exited = await new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), 4000);
    child.once("exit", () => { clearTimeout(timer); resolve(true); });
  });
  assert.equal(exited, true, "child process should exit after killNetworkChecker");
});