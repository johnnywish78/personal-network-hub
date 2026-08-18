"use strict";

// Thin API client for the local FastAPI backend.
// In Electron, window.jpnh.backendUrl() returns the base URL.
// When served in a plain browser, falls back to http://127.0.0.1:8765.

window.api = (function () {
  let baseUrl = "http://127.0.0.1:8765";

  async function init() {
    if (window.jpnh && window.jpnh.backendUrl) {
      baseUrl = await window.jpnh.backendUrl();
    }
  }

  async function request(method, path, body, raw = false) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const resp = await fetch(baseUrl + path, opts);
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const data = await resp.json();
        if (data && data.detail) detail = data.detail;
      } catch (_) {}
      throw new Error(detail || `HTTP ${resp.status}`);
    }
    return raw ? resp : resp.json();
  }

  const get = (p) => request("GET", p);
  const post = (p, body) => request("POST", p, body);
  const put = (p, body) => request("PUT", p, body);
  const patch = (p, body) => request("PATCH", p, body);
  const del = (p) => request("DELETE", p);

  return {
    init,
    get,
    post,
    put,
    patch,
    del,
    getBaseUrl: () => baseUrl,
  };
})();
