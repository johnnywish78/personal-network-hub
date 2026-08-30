"use strict";

window.Views = window.Views || {};

window.BrowserHub = (function () {
  let tabs = [];
  let activeId = null;
  let pendingOpen = null;
  let restoring = false;
  let startUrl = "about:blank";
  let findBarVisible = false;

  function tab(id) { return tabs.find((t) => t.id === id); }
  function activeTab() { return tab(activeId); }

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
      await window.api.put("/services/tabs", {
        tabs: tabs.map((t) => ({ id: t.id, url: t.url, title: t.title })),
      });
    } catch (_) { /* non-fatal */ }
  }

  async function saveFavorites() {
    try {
      const list = tabs.filter((t) => t.pinned && t.url && !t.url.startsWith("about:"));
      await window.api.put("/services/favorites", {
        favorites: list.map((t) => ({
          id: t.id,
          name: t.title || t.url,
          url: t.url,
          pinned: true,
        })),
      });
    } catch (_) { /* non-fatal */ }
  }

  async function loadFavorites() {
    try {
      const data = await window.api.get("/services/favorites");
      return (data.favorites || []).filter((f) => f.url);
    } catch (_) {
      return [];
    }
  }

  async function loadLastTabs() {
    try {
      const data = await window.api.get("/services/tabs");
      const saved = (data.tabs || []).filter((t) => t.url && t.url.startsWith("http"));
      return saved.slice(-5);
    } catch (_) {
      return [];
    }
  }

  // ---- tab management ----------------------------------------------------
  function addTab(url, title, { restore = false, pinned = false } = {}) {
    const id = mkId();
    const defaultZoom = window.BrowserSettings ? window.BrowserSettings.get("defaultZoom") / 100 : 1;
    tabs.push({
      id,
      url: url || "about:blank",
      title: title || url || "New tab",
      pinned,
      zoom: defaultZoom,
      loading: false,
    });
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

  function switchTab(direction) {
    if (tabs.length < 2) return;
    const idx = tabs.findIndex((t) => t.id === activeId);
    if (idx === -1) return;
    let next = idx + direction;
    if (next < 0) next = tabs.length - 1;
    if (next >= tabs.length) next = 0;
    activeId = tabs[next].id;
    render();
  }

  function focusAddressBar() {
    const addr = document.querySelector(".browser-address");
    if (addr) {
      addr.focus();
      addr.select();
    }
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
      const chip = el("div", "browser-tab" + (t.id === activeId ? " active" : "") + (t.loading ? " loading" : ""));
      const spinner = el("span", "tab-spinner");
      const fav = el("span", "bt-fav", t.pinned ? "\u2605" : "");
      fav.title = t.pinned ? "Pinned favorite" : "Not pinned";
      const label = el("span", "bt-label", t.title || t.url || "New tab");
      label.title = t.url;
      const close = el("button", "bt-close", "\u00D7");
      close.addEventListener("click", (e) => {
        e.stopPropagation();
        closeTab(t.id);
      });
      chip.appendChild(spinner);
      chip.appendChild(fav);
      chip.appendChild(label);
      chip.appendChild(close);
      chip.addEventListener("click", () => {
        activeId = t.id;
        render();
      });
      tabstrip.appendChild(chip);
    });

    const newBtn = el("button", "btn small ghost", "\uFF0B");
    newBtn.title = "New tab (Ctrl+T)";
    newBtn.addEventListener("click", () => {
      addTab(startUrl, "New tab");
      render();
    });
    tabstrip.appendChild(newBtn);
    tabstrip.appendChild(el("span", "spacer"));

    const active = activeTab();

    // toolbar - navigation buttons
    const mkBtn = (label, title, fn) => {
      const b = el("button", "btn small ghost", label);
      b.title = title;
      b.addEventListener("click", fn);
      toolbar.appendChild(b);
    };

    mkBtn("\u25C0", "Back (Alt+Left)", () => safeCall(activeId, "goBack"));
    mkBtn("\u25B6", "Forward (Alt+Right)", () => safeCall(activeId, "goForward"));
    mkBtn("\u27F3", "Reload (F5)", () => {
      if (active && active.loading) {
        safeCall(activeId, "stop");
      } else {
        safeCall(activeId, "reload");
      }
    });

    // home button
    mkBtn("\u2302", "Home", () => {
      if (activeId) navigateTab(activeId, startUrl);
    });

    // address bar
    const address = el("input", "mono browser-address");
    address.value = active ? active.url : "";
    address.placeholder = "Search or enter URL";
    address.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      let value = address.value.trim();
      if (!value || !activeId) return;

      let u;
      if (/^[a-z][a-z0-9+.-]*:\/\//i.test(value)) {
        u = value;
      } else if (
        /^(localhost|127(?:\.\d{1,3}){3})(:\d+)?([/].*)?$/i.test(value) ||
        /^[^\s/]+\.[^\s/]+([/].*)?$/i.test(value)
      ) {
        u = "https://" + value;
      } else {
        const engines = {
          google: "https://www.google.com/search?q=",
          duckduckgo: "https://duckduckgo.com/?q=",
          bing: "https://www.bing.com/search?q=",
          yahoo: "https://search.yahoo.com/search?p=",
          brave: "https://search.brave.com/search?q=",
          startpage: "https://www.startpage.com/do/search?q=",
        };
        const engine = window.BrowserSettings ? window.BrowserSettings.get("searchEngine") : "google";
        u = (engines[engine] || engines.google) + encodeURIComponent(value);
      }

      const t = tab(activeId);
      if (!t) return;
      t.url = u;
      t.title = u;
      saveTabs();

      const frame = document.querySelector('.browser-frame[data-tab="' + activeId + '"]');
      if (frame && frame.loadURL) {
        frame.loadURL(u);
      } else {
        render();
      }
    });
    address.addEventListener("focus", () => address.select());
    toolbar.appendChild(address);

    // pin button
    const pinBtn = el("button", "btn small" + (active && active.pinned ? "" : " ghost"), "\u2605");
    pinBtn.title = active && active.pinned ? "Unpin" : "Pin (favorite)";
    if (active && active.pinned) pinBtn.classList.add("pinned");
    pinBtn.addEventListener("click", () => activeId && togglePinned(activeId));
    toolbar.appendChild(pinBtn);

    // zoom controls
    window.ZoomControls.render(toolbar);

    // right-side buttons
    mkBtn("\u2318", "Find in page (Ctrl+F)", () => {
      const frame = getActiveFrame();
      if (frame) window.FindBar.show(frame);
    });

    mkBtn("\u2261", "Menu", () => {
      window.BrowserSettings.show();
    });

    mkBtn("\u2197", "Open in system browser", () => {
      active && openExternal(safeUrl(active.id));
    });

    root.appendChild(tabstrip);
    root.appendChild(toolbar);

    // find bar
    root.appendChild(window.FindBar.getBarElement());

    // favorites bar
    const favBar = el("div", "browser-favs");
    loadFavorites().then((favs) => {
      favs.forEach((f) => {
        const chip = el("button", "btn small chip", "\u2605 " + (f.name || f.url));
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
      frame.setAttribute("data-tab", active.id);
      frame.setAttribute("autosize", "on");
      frame.setAttribute("allowpopups", "");
      wireFrame(frame, active);
      content.appendChild(frame);
      frame.setAttribute("src", active.url);

      if (active.zoom && active.zoom !== 1) {
        frame.addEventListener("dom-ready", () => {
          frame.setZoomFactor(active.zoom);
        }, { once: true });
      }
    } else {
      content.appendChild(el("div", "empty", "No open tabs. Click \uFF0B to open one."));
    }
    root.appendChild(content);

    // download bar
    root.appendChild(window.DownloadBar.getBarElement());

    view.appendChild(root);
  }

  // ---- frame wiring ------------------------------------------------------
  function wireFrame(frame, t) {
    const { openExternal } = window.ui;

    function openInNewTab(url, title) {
      if (!url || !/^https?:\/\//i.test(url)) return;
      addTab(url, title || url);
      render();
    }

    frame.addEventListener("dom-ready", () => {
      if (t.zoom && t.zoom !== 1) {
        try { frame.setZoomFactor(t.zoom); } catch (_) {}
      }
    });

    // Handle new windows / popups -> open in new tab
    frame.addEventListener("new-window", (e) => {
      e.preventDefault();
      if (e.url && /^https?:\/\//i.test(e.url)) {
        openInNewTab(e.url, e.url);
      }
    });

    frame.addEventListener("page-title-updated", (e) => {
      if (e.title) t.title = e.title;
      saveTabsDebounced();
    });

    frame.addEventListener("did-navigate", (e) => {
      if (e.url) {
        t.url = e.url;
        syncAddress();
        saveTabsDebounced();
        trackHistory(e.url, t.title);
      }
    });

    frame.addEventListener("did-navigate-in-page", (e) => {
      if (e.url) {
        t.url = e.url;
        syncAddress();
        saveTabsDebounced();
      }
    });

    frame.addEventListener("did-start-loading", () => {
      t.loading = true;
      updateTabLoading(t.id, true);
    });

    frame.addEventListener("did-stop-loading", () => {
      t.loading = false;
      updateTabLoading(t.id, false);
    });

    // context menu
    frame.addEventListener("context-menu", (e) => {
      e.preventDefault();
      if (!window.jpnh || !window.jpnh.browser) return;
      window.jpnh.browser.showContextMenu({
        webviewId: t.id,
        x: e.x,
        y: e.y,
        linkURL: e.linkURL || "",
        srcURL: e.srcURL || "",
        mediaType: e.mediaType || "",
        text: e.selectionText || "",
        isEditable: e.isEditable || false,
        canGoBack: frame.canGoBack && frame.canGoBack(),
        canGoForward: frame.canGoForward && frame.canGoForward(),
      });
    });

    // zoom change tracking
    frame.addEventListener("did-finish-load", () => {
      try {
        const zoom = frame.getZoomFactor && frame.getZoomFactor();
        if (zoom) t.zoom = zoom;
      } catch (_) {}
    });
  }

  // ---- context menu actions -----------------------------------------------
  function handleContextAction(data) {
    const frame = document.querySelector('.browser-frame[data-tab="' + data.webviewId + '"]');
    if (!frame) return;

    switch (data.action) {
      case "open-link-new-tab":
        if (data.linkURL) addTab(data.linkURL, data.linkURL);
        render();
        break;
      case "open-link-new-window":
        if (window.jpnh && window.jpnh.openExternal) window.jpnh.openExternal(data.linkURL);
        break;
      case "copy-link":
        if (window.jpnh && window.jpnh.openExternal) {
          navigator.clipboard.writeText(data.linkURL);
        }
        break;
      case "copy":
        navigator.clipboard.writeText(data.text || "");
        break;
      case "open-image-new-tab":
        if (data.srcURL) addTab(data.srcURL, data.srcURL);
        render();
        break;
      case "save-image":
        if (data.srcURL && window.jpnh && window.jpnh.browser) {
          window.jpnh.browser.download(data.srcURL);
        }
        break;
      case "copy-image":
      case "copy-image-address":
        navigator.clipboard.writeText(data.srcURL || "");
        break;
      case "go-back":
        if (frame.goBack) frame.goBack();
        break;
      case "go-forward":
        if (frame.goForward) frame.goForward();
        break;
      case "reload":
        if (frame.reload) frame.reload();
        break;
      case "save-page":
        if (frame.getURL && window.jpnh && window.jpnh.browser) {
          window.jpnh.browser.download(frame.getURL());
        }
        break;
      case "print":
        if (window.jpnh && window.jpnh.browser) window.jpnh.browser.print();
        break;
      case "view-source":
        if (frame.getURL) {
          addTab("view-source:" + frame.getURL(), "View Source");
          render();
        }
        break;
      case "inspect":
        if (frame.openDevTools) frame.openDevTools();
        break;
    }
  }

  // ---- history tracking ---------------------------------------------------
  function trackHistory(url, title) {
    if (window.jpnh && window.jpnh.browser) {
      window.jpnh.browser.addHistory(url, title);
    }
  }

  // ---- zoom ---------------------------------------------------------------
  function applyZoomToActive(level) {
    const t = activeTab();
    if (!t) return;
    t.zoom = level;
    const frame = getActiveFrame();
    if (frame && frame.setZoomFactor) {
      frame.setZoomFactor(level);
    }
    window.ZoomControls.setZoom(level);
  }

  // ---- helpers -----------------------------------------------------------
  let saveTimer = null;
  function saveTabsDebounced() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveTabs, 600);
  }

  function syncAddress() {
    const t = activeTab();
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
      const frame = document.querySelector('.browser-frame[data-tab="' + id + '"]');
      if (frame && frame[method]) frame[method]();
    } catch (_) { /* ignore */ }
  }

  function getActiveFrame() {
    if (!activeId) return null;
    return document.querySelector('.browser-frame[data-tab="' + activeId + '"]');
  }

  function openInActive(url, title) {
    if (activeId) {
      const t = tab(activeId);
      if (t) {
        t.url = url;
        t.title = title || url;
        saveTabs();
        render();
      }
    } else {
      addTab(url, title);
      render();
    }
  }

  function updateTabLoading(id, loading) {
    const chips = document.querySelectorAll(".browser-tab");
    chips.forEach((chip) => {
      const label = chip.querySelector(".bt-label");
      const t = tabs.find((t) => label && label.textContent === (t.title || t.url || "New tab"));
      if (t && t.id === id) {
        if (loading) chip.classList.add("loading");
        else chip.classList.remove("loading");
      }
    });
  }

  // ---- keyboard shortcuts -------------------------------------------------
  function setupKeyboardShortcuts() {
    document.addEventListener("keydown", (e) => {
      if (!document.querySelector(".browser-hub")) return;

      const isInput = e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA";

      // Ctrl+T: New tab
      if (e.ctrlKey && e.key === "t") {
        e.preventDefault();
        addTab(startUrl, "New tab");
        render();
        return;
      }

      // Ctrl+W: Close tab
      if (e.ctrlKey && e.key === "w") {
        e.preventDefault();
        if (activeId) closeTab(activeId);
        return;
      }

      // Ctrl+Tab: Next tab
      if (e.ctrlKey && !e.shiftKey && e.key === "Tab") {
        e.preventDefault();
        switchTab(1);
        return;
      }

      // Ctrl+Shift+Tab: Previous tab
      if (e.ctrlKey && e.shiftKey && e.key === "Tab") {
        e.preventDefault();
        switchTab(-1);
        return;
      }

      // Ctrl+L: Focus address bar
      if (e.ctrlKey && e.key === "l") {
        e.preventDefault();
        focusAddressBar();
        return;
      }

      // F5 / Ctrl+R: Reload
      if (e.key === "F5" || (e.ctrlKey && e.key === "r")) {
        e.preventDefault();
        const t = activeTab();
        if (t && t.loading) {
          safeCall(activeId, "stop");
        } else {
          safeCall(activeId, "reload");
        }
        return;
      }

      // F12: DevTools
      if (e.key === "F12") {
        e.preventDefault();
        const frame = getActiveFrame();
        if (frame && frame.openDevTools) frame.openDevTools();
        return;
      }

      // Ctrl+F: Find in page
      if (e.ctrlKey && e.key === "f" && !isInput) {
        e.preventDefault();
        const frame = getActiveFrame();
        if (frame) window.FindBar.show(frame);
        return;
      }

      // Escape: Close find bar
      if (e.key === "Escape" && window.FindBar.isVisible()) {
        window.FindBar.hide();
        return;
      }

      // Ctrl++: Zoom in
      if (e.ctrlKey && (e.key === "+" || e.key === "=")) {
        e.preventDefault();
        applyZoomToActive(window.ZoomControls.zoomIn());
        return;
      }

      // Ctrl+-: Zoom out
      if (e.ctrlKey && e.key === "-") {
        e.preventDefault();
        applyZoomToActive(window.ZoomControls.zoomOut());
        return;
      }

      // Ctrl+0: Reset zoom
      if (e.ctrlKey && e.key === "0") {
        e.preventDefault();
        applyZoomToActive(window.ZoomControls.reset());
        return;
      }

      // Ctrl+P: Print
      if (e.ctrlKey && e.key === "p") {
        e.preventDefault();
        if (window.jpnh && window.jpnh.browser) window.jpnh.browser.print();
        return;
      }

      // Alt+Left: Back
      if (e.altKey && e.key === "ArrowLeft") {
        e.preventDefault();
        safeCall(activeId, "goBack");
        return;
      }

      // Alt+Right: Forward
      if (e.altKey && e.key === "ArrowRight") {
        e.preventDefault();
        safeCall(activeId, "goForward");
        return;
      }

      // Ctrl+Shift+Delete: Clear browsing data
      if (e.ctrlKey && e.shiftKey && e.key === "Delete") {
        e.preventDefault();
        window.BrowserSettings.show();
        return;
      }
    });
  }

  // ---- IPC listeners ------------------------------------------------------
  function setupIPC() {
    if (!window.jpnh) return;

    // Context menu actions
    if (window.jpnh.onContextMenuAction) {
      window.jpnh.onContextMenuAction(handleContextAction);
    }

    // Downloads
    if (window.jpnh.onDownloadStarted) {
      window.jpnh.onDownloadStarted((data) => {
        window.DownloadBar.addDownload(data);
      });
    }
    if (window.jpnh.onDownloadProgress) {
      window.jpnh.onDownloadProgress((data) => {
        window.DownloadBar.updateProgress(data.id, data.progress, data.receivedBytes, data.totalBytes);
      });
    }
    if (window.jpnh.onDownloadComplete) {
      window.jpnh.onDownloadComplete((data) => {
        window.DownloadBar.complete(data.id, data.state, data.savePath);
      });
    }

    // Permissions
    if (window.jpnh.onPermissionRequest) {
      window.jpnh.onPermissionRequest((data) => {
        showPermissionDialog(data);
      });
    }

    // Open links in new tabs (from main process webview interception)
    if (window.jpnh.onBrowserOpenInTab) {
      window.jpnh.onBrowserOpenInTab((data) => {
        if (data && data.url) {
          addTab(data.url, data.url);
          render();
        }
      });
    }
  }

  function showPermissionDialog(data) {
    const { el } = window.ui;
    const label = window.BrowserPermissions
      ? window.BrowserPermissions.getLabel(data.permission)
      : data.permission;

    const dialog = el("div", "permission-dialog");
    dialog.innerHTML = "";
    dialog.appendChild(el("h4", "", "Permission Request"));
    dialog.appendChild(el("p", "", "This site wants to use: " + label));
    dialog.appendChild(el("p", "dim", data.requestingUrl || ""));

    const actions = el("div", "actions");
    const denyBtn = el("button", "btn small", "Deny");
    const allowBtn = el("button", "btn small primary", "Allow");

    denyBtn.addEventListener("click", () => {
      if (window.jpnh && window.jpnh.browser) {
        window.jpnh.browser.respondPermission(data.id, false);
      }
      dialog.remove();
    });

    allowBtn.addEventListener("click", () => {
      if (window.jpnh && window.jpnh.browser) {
        window.jpnh.browser.respondPermission(data.id, true);
      }
      dialog.remove();
    });

    actions.appendChild(denyBtn);
    actions.appendChild(allowBtn);
    dialog.appendChild(actions);

    document.body.appendChild(dialog);
    setTimeout(() => {
      if (dialog.parentElement) dialog.remove();
    }, 30000);
  }

  // ---- view entry --------------------------------------------------------
  return {
    async render(container, params) {
      setupKeyboardShortcuts();
      setupIPC();

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
    applyZoomToActive,
  };
})();

window.Views.browser = {
  async render(container, params) {
    await window.BrowserHub.render(container, params);
  },
};
