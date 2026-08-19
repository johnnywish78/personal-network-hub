"use strict";

// Browser Hub: tab-based embedded browser.
// - multi-tab webviews (persistent partition)
// - address bar with back / forward / reload
// - favorites with pinning, restore of last open tabs
// - external open in the system browser

window.Views = window.Views || {};

window.BrowserHub = (function () {
  let tabs = [];        // [{id, url, title}]
  let activeId = null;
  let pendingOpen = null;
  let restoring = false;
  let startUrl = "about:blank";

  function tab(id) { return tabs.find((t) => t.id === id); }

  function mkId() {
    return "tab-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  }

  function setStart(url) { startUrl = url || "about:blank"; }

  function queueOpen(url, title) {
    pendingOpen = { url, title };
    if (window.navigate) window.navigate("browser");
    else return true;
    return true;
  }

  // ---- persistence -------------------------------------------------------
  async function saveTabs() {
    try {
      await window.api.put("/services/tabs", { tabs: tabs.map((t) => ({ id: t.id, url: t.url, title: t.title })) });
    } catch (_) { /* non-fatal */ }
  }

  async function saveFavorites() {
    try {
      const list = tabs.filter((t) => t.pinned && t.url && !t.url.startsWith("about:"));
      await window.api.put("/services/favorites", { favorites: list.map((t) => ({ id: t.id, name: t.title || t.url, url: t.url, pinned: true })) });
    } catch (_) { /* non-fatal */ }
  }

  async function loadFavorites() {
    try {
      const data = await window.api.get("/services/favorites");
      return (data.favorites || []).filter((f) => f.url);
    } catch (_) { return []; }
  }

  async function loadLastTabs() {
    try {
      const data = await window.api.get("/services/tabs");
      const saved = (data.tabs || []).filter((t) => t.url && t.url.startsWith("http"));
      return saved.slice(-5);
    } catch (_) { return []; }
  }

  // ---- tab management ----------------------------------------------------
  function addTab(url, title, { restore = false, pinned = false } = {}) {
    const id = mkId();
    tabs.push({ id, url: url || "about:blank", title: title || url || "New tab", pinned });
    activeId = id;
    if (!restore) saveTabs();
    return id;
  }

  function closeTab(id) {
    const idx = tabs.findIndex((t) => t.id === id);
    if (idx === -1) return;
    tabs.splice(idx, 1);
    if (activeId === id) {
      activeId = tabs.length ? tabs[idx === tabs.length ? idx - 1 : idx].id : null;
    }
    saveTabs();
    render();
  }

  function togglePinned(id) {
    const t = tab(id);
    if (t) {
      t.pinned = !t.pinned;
      saveFavorites();
      render();
    }
  }

  function navigateTab(id, url) {
    const t = tab(id);
    if (!t || !url) return;
    t.url = url;
    t.title = url;
    saveTabs();
    render();
  }

  // ---- render ------------------------------------------------------------
  function render() {
    const view = document.getElementById("view");
    const { el, openExternal } = window.ui;
    view.replaceChildren();

    const root = el("div", "browser-hub");
    const tabstrip = el("div", "browser-tabs");
    const toolbar = el("div", "browser-toolbar");

    // tabs
    tabs.forEach((t) => {
      const chip = el("div", "browser-tab" + (t.id === activeId ? " active" : ""));
      const fav = el("span", "bt-fav", t.pinned ? "★" : "");
      fav.title = t.pinned ? "Pinned favorite (remove to unpin)" : "Not pinned";
      const label = el("span", "bt-label", t.title || t.url || "New tab");
      label.title = t.url;
      const close = el("button", "bt-close", "×");
      close.addEventListener("click", (e) => { e.stopPropagation(); closeTab(t.id); });
      chip.appendChild(fav);
      chip.appendChild(label);
      chip.appendChild(close);
      chip.addEventListener("click", () => { activeId = t.id; render(); });
      tabstrip.appendChild(chip);
    });

    const newBtn = el("button", "btn small ghost", "＋");
    newBtn.title = "New tab";
    newBtn.addEventListener("click", () => { addTab(startUrl, "New tab"); render(); });
    tabstrip.appendChild(newBtn);
    tabstrip.appendChild(el("span", "spacer"));

    const active = tab(activeId);

    // toolbar buttons
    const mkBtn = (label, title, fn) => {
      const b = el("button", "btn small ghost", label);
      b.title = title;
      b.addEventListener("click", fn);
      toolbar.appendChild(b);
    };
    mkBtn("◀", "Back", () => safeCall(activeId, "goBack"));
    mkBtn("▶", "Forward", () => safeCall(activeId, "goForward"));
    mkBtn("⟳", "Reload", () => safeCall(activeId, "reload"));

    const address = el("input", "mono browser-address");
    address.value = active ? active.url : "";
    address.placeholder = "Enter a URL and press Enter";
    address.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        let u = address.value.trim();
        if (!u) return;
        if (!/^[a-z]+:\/\//i.test(u)) u = "https://" + u;
        if (activeId) {
          const t = tab(activeId);
          if (t) { t.url = u; t.title = u; saveTabs(); render(); }
        }
      }
    });
    toolbar.appendChild(address);

    const pinBtn = el("button", "btn small" + (active && active.pinned ? "" : " ghost"), "★");
    pinBtn.title = active && active.pinned ? "Unpin / unfavorite" : "Favorite (pinned)";
    if (active && active.pinned) pinBtn.classList.add("pinned");
    pinBtn.addEventListener("click", () => activeId && togglePinned(activeId));
    toolbar.appendChild(pinBtn);

    mkBtn("↗", "Open in system browser", () => active && openExternal(safeUrl(active.id)));

    root.appendChild(tabstrip);
    root.appendChild(toolbar);

    // favorites bar (restored favorites)
    const favBar = el("div", "browser-favs");
    loadFavorites().then((favs) => {
      favs.forEach((f) => {
        const chip = el("button", "btn small chip", "★ " + (f.name || f.url));
        chip.title = f.url;
        chip.addEventListener("click", () => openInActive(f.url, f.name));
        favBar.appendChild(chip);
      });
    });
    root.appendChild(favBar);

    // content area
    const content = el("div", "browser-content");
    if (active) {
      const frame = el("webview");
      frame.setAttribute("partition", "persist:jpnh");
      frame.setAttribute("class", "browser-frame");
      wireFrame(frame, active);
      content.appendChild(frame);
      frame.setAttribute("src", active.url);
    } else {
      content.appendChild(el("div", "empty", "No open tabs. Click ＋ to open one."));
    }
    root.appendChild(content);
    view.appendChild(root);
  }

  function wireFrame(frame, t) {
    const { openExternal } = window.ui;
    frame.addEventListener("dom-ready", () => {
      try {
        const wc = frame.getWebContents && frame.getWebContents();
        if (wc && wc.setWindowOpenHandler) {
          wc.setWindowOpenHandler(({ url }) => { openExternal(url); return { action: "deny" }; });
        }
      } catch (_) { /* ignore */ }
    });
    frame.addEventListener("new-window", (e) => { if (e.url) openExternal(e.url); });
    frame.addEventListener("page-title-updated", (e) => {
      if (e.title) { t.title = e.title; const lab = frame.parentElement && frame.parentElement.parentElement; }
      saveTabsDebounced();
    });
    frame.addEventListener("did-navigate", (e) => {
      if (e.url) { t.url = e.url; syncAddress(); saveTabsDebounced(); }
    });
    frame.addEventListener("did-navigate-in-page", (e) => {
      if (e.url) { t.url = e.url; syncAddress(); saveTabsDebounced(); }
    });
  }

  let saveTimer = null;
  function saveTabsDebounced() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveTabs, 600);
  }

  function syncAddress() {
    const t = tab(activeId);
    const addr = document.querySelector(".browser-address");
    if (addr && t) addr.value = t.url;
  }

  function safeUrl(id) {
    const t = tab(id);
    if (!t) return "";
    try {
      const f = document.querySelector('.browser-frame[data-tab="' + id + '"]');
      if (f && f.getURL) return f.getURL() || t.url;
    } catch (_) { /* ignore */ }
    return t.url;
  }

  function safeCall(id, method) {
    try {
      const frames = document.querySelectorAll(".browser-frame");
      frames.forEach((f) => { if (f[method]) f[method](); });
    } catch (_) { /* ignore */ }
  }

  function openInActive(url, title) {
    if (activeId) {
      const t = tab(activeId);
      if (t) { t.url = url; t.title = title || url; saveTabs(); render(); }
    } else {
      addTab(url, title);
      render();
    }
  }

  // ---- view entry --------------------------------------------------------
  return {
    async render(container, params) {
      if (pendingOpen) {
        const p = pendingOpen;
        pendingOpen = null;
        addTab(p.url, p.title || p.url);
      } else if (!tabs.length) {
        restoring = true;
        const last = await loadLastTabs();
        if (last.length) {
          last.forEach((t) => addTab(t.url, t.title || t.url, { restore: true }));
        } else {
          addTab(startUrl, "New tab");
        }
        restoring = false;
      }
      render();
    },
    queueOpen,
    setStart,
  };
})();

window.Views.browser = {
  async render(container, params) {
    await window.BrowserHub.render(container, params);
  },
};