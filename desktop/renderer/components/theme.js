"use strict";

// Theme manager: System / Dark / Light.
// Persisted in localStorage under "jpnh-theme" (default "system").
// Applies the resolved (dark | light) theme to <html data-theme="...">.
// In System mode it follows prefers-color-scheme and updates on OS changes.

window.Theme = (function () {
  const KEY = "jpnh-theme";
  const MQL = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  let mode = "system";
  const listeners = [];

  function readStored() {
    try {
      const v = localStorage.getItem(KEY);
      return v === "dark" || v === "light" || v === "system" ? v : "system";
    } catch (_) {
      return "system";
    }
  }

  function resolve(m) {
    if (m === "system") return MQL && MQL.matches ? "dark" : "light";
    return m;
  }

  function apply() {
    const theme = resolve(mode);
    document.documentElement.setAttribute("data-theme", theme);
    return theme;
  }

  function getMode() {
    return mode;
  }

  function getTheme() {
    return resolve(mode);
  }

  function setMode(m) {
    mode = m === "dark" || m === "light" || m === "system" ? m : "system";
    try {
      localStorage.setItem(KEY, mode);
    } catch (_) { /* storage may be unavailable */ }
    apply();
    listeners.forEach((fn) => fn(mode));
  }

  function onChange(fn) {
    listeners.push(fn);
  }

  if (MQL) {
    MQL.addEventListener("change", () => {
      if (mode === "system") {
        apply();
        listeners.forEach((fn) => fn(mode));
      }
    });
  }

  mode = readStored();
  apply();

  return { getMode, getTheme, setMode, onChange, KEY };
})();