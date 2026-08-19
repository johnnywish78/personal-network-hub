"use strict";

// Unit tests for the pure-Node backend process manager.
// Run with:  node --test test/

const test = require("node:test");
const assert = require("node:assert");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const { spawn } = require("node:child_process");

const bm = require("../lib/backend-manager");

test("platformDir maps win32/linux/darwin", () => {
  assert.equal(bm.platformDir("win32"), "win");
  assert.equal(bm.platformDir("linux"), "linux");
  assert.equal(bm.platformDir("darwin"), "mac");
});

test("exeName returns .exe on windows", () => {
  assert.equal(bm.exeName("win32"), "jpnh-backend.exe");
  assert.equal(bm.exeName("linux"), "jpnh-backend");
});

test("resolveBackendExecutable uses resourcesPath in packaged mode", () => {
  const p = bm.resolveBackendExecutable({
    isPackaged: true,
    dev: false,
    rootDir: "/project",
    resourcesPath: "/opt/JPNH/resources",
  });
  const expected = process.platform === "win32"
    ? path.join("/opt/JPNH/resources", "backend", "win", "jpnh-backend.exe")
    : path.join("/opt/JPNH/resources", "backend", "linux", "jpnh-backend");
  assert.equal(p, expected);
});

test("buildCommand uses python module in dev mode", () => {
  const cmd = bm.buildCommand({
    isPackaged: false,
    dev: false,
    rootDir: "/project",
    resourcesPath: "/x",
    host: "127.0.0.1",
    port: 9000,
  });
  assert.equal(cmd.args[0], "-m");
  assert.equal(cmd.args[1], "backend.main");
  assert.ok(cmd.args.includes("9000"));
  assert.equal(cmd.cwd, "/project");
});

test("findFreePort returns the preferred port when free", async () => {
  const port = await bm.findFreePort({ base: 45671, host: "127.0.0.1", maxOffset: 5 });
  assert.equal(port, 45671);
});

test("findFreePort skips an occupied port", async () => {
  const blocker = net.createServer();
  await new Promise((r) => blocker.listen(0, "127.0.0.1", r));
  const base = blocker.address().port;
  const chosen = await bm.findFreePort({ base, host: "127.0.0.1", maxOffset: 10 });
  assert.notEqual(chosen, base);
  blocker.close();
});

test("waitForReady resolves once /ping returns 200", async () => {
  const server = http.createServer((req, res) => {
    if (req.url === "/ping") { res.writeHead(200); res.end("pong"); }
    else { res.writeHead(404); res.end(); }
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const port = server.address().port;
  const ok = await bm.waitForReady({ host: "127.0.0.1", port, timeoutMs: 3000 });
  assert.equal(ok, true);
  server.close();
});

test("waitForReady rejects on timeout when nothing is listening", async () => {
  const port = 47593; // assumed free in test env
  await assert.rejects(
    () => bm.waitForReady({ host: "127.0.0.1", port, timeoutMs: 1200 }),
    /did not become ready/
  );
});

test("killBackend terminates a spawned child process group", async () => {
  const child = spawn(process.execPath, ["-e", "setInterval(()=>{},1000)"], {
    stdio: "ignore",
    detached: process.platform !== "win32",
    windowsHide: true,
  });
  bm.killBackend(child, process.platform);
  const exited = await new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), 4000);
    child.once("exit", () => { clearTimeout(timer); resolve(true); });
  });
  assert.equal(exited, true, "child process should exit after killBackend");
});

test("prepareBackend picks a free port and builds args", async () => {
  const prep = await bm.prepareBackend({
    isPackaged: true,
    dev: false,
    rootDir: "/project",
    resourcesPath: "/opt/JPNH/resources",
    host: "127.0.0.1",
    basePort: 8777,
    maxOffset: 5,
  });
  assert.equal(typeof prep.port, "number");
  assert.ok(prep.args.includes(String(prep.port)));
  assert.ok(prep.command.includes("jpnh-backend"));
});