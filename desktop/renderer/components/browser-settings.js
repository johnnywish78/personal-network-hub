"use strict";

window.BrowserSettings = (function () {
  let overlayEl = null;

  const DEFAULTS = {
    homepage: "about:blank",
    startup: "lastTabs",
    searchEngine: "google",
    theme: "dark",
    showBookmarksBar: true,
    fontSize: "medium",
    defaultZoom: 100,
    doNotTrack: false,
    safeBrowsing: true,
    acceptCookies: true,
    clearOnExit: [],
    javascript: true,
    images: true,
    popups: false,
    notifications: true,
    location: true,
    camera: "ask",
    microphone: "ask",
    downloadLocation: "~/Downloads",
    askDownloadLocation: true,
    language: "en",
    smoothScrolling: true,
  };

  let s = {};
  function load() { try { s = { ...DEFAULTS, ...JSON.parse(localStorage.getItem("browser-settings") || "{}") }; } catch (_) { s = { ...DEFAULTS }; } }
  function save() { try { localStorage.setItem("browser-settings", JSON.stringify(s)); } catch (_) {} }
  function get(k) { return s[k]; }
  function set(k, v) {
    s[k] = v;
    save();
    applyToApp(k, v);
  }

  function applyToApp(k, v) {
    // Theme - sync with main app Theme system
    if (k === "theme" && window.Theme) {
      window.Theme.setMode(v);
    }

    // Font size - apply to body
    if (k === "fontSize") {
      var sizes = { small: "12px", medium: "14px", large: "16px" };
      document.documentElement.style.fontSize = sizes[v] || sizes.medium;
    }

    // Zoom - apply to body
    if (k === "defaultZoom") {
      document.body.style.zoom = (v / 100).toString();
    }

    // Smooth scrolling
    if (k === "smoothScrolling") {
      document.documentElement.style.scrollBehavior = v ? "smooth" : "auto";
    }
  }

  function applyAll() {
    Object.keys(s).forEach(function (k) { applyToApp(k, s[k]); });
  }

  // ---- helpers -----------------------------------------------------------
  function h(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
  }

  function section(parent, title) {
    const d = h("div", "settings-section-title", title);
    parent.appendChild(d);
    return parent;
  }

  function row(parent, label, ctrl) {
    const r = h("div", "settings-row");
    r.appendChild(h("span", "settings-label", label));
    const c = h("div", "settings-control");
    c.appendChild(ctrl);
    r.appendChild(c);
    parent.appendChild(r);
    return r;
  }

  function toggle(parent, label, key) {
    const wrap = h("div", "settings-row");
    wrap.appendChild(h("span", "settings-label", label));
    const sw = h("label", "toggle-switch");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = !!s[key];
    cb.dataset.key = key;
    const sl = h("span", "toggle-slider");
    sw.appendChild(cb);
    sw.appendChild(sl);
    wrap.appendChild(sw);
    parent.appendChild(wrap);
    cb.addEventListener("change", function () { set(this.dataset.key, this.checked); });
    return wrap;
  }

  function select(parent, label, key, opts) {
    const sel = document.createElement("select");
    sel.dataset.key = key;
    opts.forEach(function (o) {
      const opt = document.createElement("option");
      opt.value = o[0];
      opt.textContent = o[1];
      if (s[key] === o[0]) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.addEventListener("change", function () { set(this.dataset.key, this.value); });
    row(parent, label, sel);
    return sel;
  }

  function input(parent, label, key, ph) {
    const inp = document.createElement("input");
    inp.type = "text";
    inp.value = s[key] || "";
    inp.placeholder = ph || "";
    inp.dataset.key = key;
    inp.addEventListener("change", function () { set(this.dataset.key, this.value); });
    row(parent, label, inp);
    return inp;
  }

  function range(parent, label, key, min, max, step) {
    const wrap = h("div", "range-wrap");
    const inp = document.createElement("input");
    inp.type = "range";
    inp.min = String(min);
    inp.max = String(max);
    inp.step = String(step);
    inp.value = String(s[key] || 100);
    inp.dataset.key = key;
    const val = h("span", "range-value", inp.value + "%");
    inp.addEventListener("input", function () {
      set(this.dataset.key, Number(this.value));
      val.textContent = this.value + "%";
    });
    wrap.appendChild(inp);
    wrap.appendChild(val);
    row(parent, label, wrap);
  }

  function btn(parent, label, cls, fn) {
    const b = h("button", "btn " + (cls || "small"), label);
    b.addEventListener("click", fn);
    parent.appendChild(b);
    return b;
  }

  function divider(parent) { parent.appendChild(h("div", "settings-divider")); }
  function subtitle(parent, t) { parent.appendChild(h("div", "settings-subtitle", t)); }
  function hint(parent, t) { parent.appendChild(h("p", "settings-hint", t)); }

  // ---- sections ----------------------------------------------------------
  function renderGeneral(p) {
    section(p, "General");
    select(p, "On startup", "startup", [
      ["lastTabs", "Continue where you left off"],
      ["homepage", "Open a specific page"],
      ["newTab", "Open the New Tab page"],
    ]);
    input(p, "Homepage URL", "homepage", "about:blank");
    divider(p);
    btn(p, "Reset to defaults", "btn small ghost", function () {
      s = { ...DEFAULTS }; save();
      overlayEl.remove(); overlayEl = null; show();
    });
  }

  function renderSearch(p) {
    section(p, "Search engine");
    select(p, "Default search engine", "searchEngine", [
      ["google", "Google"],
      ["duckduckgo", "DuckDuckGo"],
      ["bing", "Bing"],
      ["yahoo", "Yahoo"],
      ["brave", "Brave Search"],
      ["startpage", "Startpage"],
    ]);
    hint(p, "Used when typing in the address bar");
  }

  function renderAppearance(p) {
    section(p, "Appearance");
    select(p, "Theme", "theme", [["dark", "Dark"], ["light", "Light"]]);
    toggle(p, "Show bookmarks bar", "showBookmarksBar");
    select(p, "Font size", "fontSize", [["small", "Small"], ["medium", "Medium"], ["large", "Large"]]);
    range(p, "Default zoom", "defaultZoom", 50, 200, 10);
    toggle(p, "Smooth scrolling", "smoothScrolling");
  }

  function renderPrivacy(p) {
    section(p, "Privacy & Security");

    subtitle(p, "Clear browsing data");
    var clearOpts = [
      ["cache", "Cached images and files"],
      ["cookies", "Cookies and other site data"],
      ["history", "Browsing history"],
      ["passwords", "Passwords"],
      ["formdata", "Autofill form data"],
      ["siteSettings", "Site settings"],
    ];

    var cbs = [];
    clearOpts.forEach(function (o) {
      var row = h("div", "settings-checkbox-row");
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = o[0] === "cache" || o[0] === "cookies";
      cb.id = "cs-" + o[0];
      var lbl = document.createElement("label");
      lbl.htmlFor = "cs-" + o[0];
      lbl.textContent = o[1];
      row.appendChild(cb);
      row.appendChild(lbl);
      p.appendChild(row);
      cbs.push({ key: o[0], cb: cb });
    });

    var timeRow = h("div", "settings-row");
    timeRow.appendChild(h("span", "settings-label", "Time range"));
    var timeSel = document.createElement("select");
    [["lastHour", "Last hour"], ["lastDay", "Last 24 hours"], ["lastWeek", "Last 7 days"], ["lastMonth", "Last 4 weeks"], ["allTime", "All time"]].forEach(function (o) {
      var opt = document.createElement("option");
      opt.value = o[0]; opt.textContent = o[1];
      timeSel.appendChild(opt);
    });
    var tc = h("div", "settings-control"); tc.appendChild(timeSel);
    timeRow.appendChild(tc);
    p.appendChild(timeRow);

    btn(p, "Clear browsing data", "btn danger", function () {
      var types = cbs.filter(function (c) { return c.cb.checked; }).map(function (c) { return c.key; });
      if (types.length === 0) return;
      if (window.jpnh && window.jpnh.browser) window.jpnh.browser.clearData(types);
      if (window.showToast) window.showToast("Browsing data cleared", "ok");
    });

    divider(p);
    subtitle(p, "Privacy");
    toggle(p, "Do Not Track", "doNotTrack");
    toggle(p, "Safe Browsing", "safeBrowsing");
    toggle(p, "Accept cookies", "acceptCookies");

    divider(p);
    subtitle(p, "On exit");
    [["cache", "Clear cached images"], ["cookies", "Clear cookies"], ["history", "Clear history"]].forEach(function (o) {
      var r = h("div", "settings-checkbox-row");
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = (s.clearOnExit || []).indexOf(o[0]) >= 0;
      cb.dataset.clearKey = o[0];
      var lbl = document.createElement("label");
      lbl.textContent = o[1];
      r.appendChild(cb);
      r.appendChild(lbl);
      p.appendChild(r);
      cb.addEventListener("change", function () {
        var arr = s.clearOnExit || [];
        if (this.checked) arr.push(this.dataset.clearKey);
        else arr = arr.filter(function (k) { return k !== this.dataset.clearKey; }.bind(this));
        s.clearOnExit = arr;
        save();
      });
    });
  }

  function renderContent(p) {
    section(p, "Content Settings");
    toggle(p, "JavaScript", "javascript");
    hint(p, "Some sites may not work without JavaScript");
    toggle(p, "Images", "images");
    toggle(p, "Pop-ups and redirects", "popups");
    divider(p);
    subtitle(p, "Permissions");
    toggle(p, "Notifications", "notifications");
    select(p, "Location", "location", [["ask", "Ask"], ["allow", "Allow"], ["block", "Block"]]);
    select(p, "Camera", "camera", [["ask", "Ask"], ["allow", "Allow"], ["block", "Block"]]);
    select(p, "Microphone", "microphone", [["ask", "Ask"], ["allow", "Allow"], ["block", "Block"]]);
    divider(p);
    btn(p, "Reset all content settings", "btn small ghost", function () {
      ["javascript", "images", "notifications"].forEach(function (k) { s[k] = true; });
      s.popups = false;
      ["location", "camera", "microphone"].forEach(function (k) { s[k] = "ask"; });
      save();
      overlayEl.remove(); overlayEl = null; show();
    });
  }

  function renderDownloads(p) {
    section(p, "Downloads");
    input(p, "Download location", "downloadLocation", "~/Downloads");
    toggle(p, "Ask where to save each file", "askDownloadLocation");
  }

  function renderLanguage(p) {
    section(p, "Language");
    select(p, "Display language", "language", [
      ["en", "English"], ["fa", "Persian (Farsi)"], ["ar", "Arabic"],
      ["fr", "French"], ["de", "German"], ["es", "Spanish"],
      ["pt", "Portuguese"], ["ru", "Russian"], ["zh", "Chinese"],
      ["ja", "Japanese"], ["ko", "Korean"], ["tr", "Turkish"], ["hi", "Hindi"],
    ]);
    hint(p, "Restart the app to apply language changes");
  }

  function renderShortcuts(p) {
    section(p, "Keyboard Shortcuts");
    var t = h("table", "settings-table");
    t.innerHTML = "<thead><tr><th>Shortcut</th><th>Action</th></tr></thead>";
    var tb = document.createElement("tbody");
    [
      ["Ctrl + T", "New tab"], ["Ctrl + W", "Close tab"],
      ["Ctrl + Tab", "Next tab"], ["Ctrl + Shift + Tab", "Previous tab"],
      ["Ctrl + L", "Focus address bar"], ["F5 / Ctrl + R", "Reload"],
      ["F12", "DevTools"], ["Ctrl + F", "Find in page"],
      ["Ctrl + +", "Zoom in"], ["Ctrl + -", "Zoom out"],
      ["Ctrl + 0", "Reset zoom"], ["Ctrl + P", "Print"],
      ["Alt + Left", "Go back"], ["Alt + Right", "Go forward"],
      ["Ctrl + Shift + Delete", "Clear data"], ["Escape", "Close find/menu"],
    ].forEach(function (s) {
      var tr = document.createElement("tr");
      tr.innerHTML = "<td><kbd>" + s[0] + "</kbd></td><td>" + s[1] + "</td>";
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    p.appendChild(t);
  }

  function renderAbout(p) {
    section(p, "About");
    p.appendChild(h("p", "", "Johnny Personal Network Hub"));
    p.appendChild(h("p", "muted", "Version 0.1.0"));
    p.appendChild(h("p", "muted", "Built with Electron + Chromium + Node.js"));
    divider(p);
    p.appendChild(h("p", "settings-subtitle", "Links"));
    ["Homepage", "Report issue"].forEach(function (label, i) {
      var url = ["https://github.com/johnny/personal-network-hub", "https://github.com/johnny/personal-network-hub/issues"][i];
      var a = document.createElement("a");
      a.href = "#"; a.textContent = label; a.style.color = "var(--accent)";
      a.style.display = "block"; a.style.marginBottom = "4px";
      a.addEventListener("click", function (e) { e.preventDefault(); if (window.jpnh) window.jpnh.openExternal(url); });
      p.appendChild(a);
    });
  }

  var RENDERERS = {
    general: renderGeneral, search: renderSearch, appearance: renderAppearance,
    privacy: renderPrivacy, content: renderContent, downloads: renderDownloads,
    language: renderLanguage, shortcuts: renderShortcuts, about: renderAbout,
  };

  var NAV_ITEMS = [
    { id: "general", icon: "\u2699", label: "General" },
    { id: "search", icon: "\uD83D\uDD0D", label: "Search engine" },
    { id: "appearance", icon: "\uD83C\uDFA8", label: "Appearance" },
    { id: "privacy", icon: "\uD83D\uDD12", label: "Privacy & Security" },
    { id: "content", icon: "\uD83D\uDCC4", label: "Content settings" },
    { id: "downloads", icon: "\u2B07", label: "Downloads" },
    { id: "language", icon: "\uD83C\uDF10", label: "Language" },
    { id: "shortcuts", icon: "\u2328", label: "Shortcuts" },
    { id: "about", icon: "\u2139", label: "About" },
  ];

  function show() {
    if (overlayEl) { overlayEl.remove(); overlayEl = null; }
    load();

    overlayEl = h("div", "browser-settings");

    var panel = h("div", "browser-settings-content");

    // header
    var head = h("div", "settings-header");
    head.appendChild(h("span", "settings-header-title", "Settings"));
    var closeBtn = h("button", "btn small ghost", "\u2715");
    closeBtn.addEventListener("click", hide);
    head.appendChild(closeBtn);
    panel.appendChild(head);

    // layout
    var layout = h("div", "settings-layout");

    // sidebar
    var sidebar = h("div", "settings-sidebar");
    var content = h("div", "settings-content");
    var active = "general";

    function render(id) {
      active = id;
      content.innerHTML = "";
      sidebar.querySelectorAll(".settings-nav-item").forEach(function (n) {
        n.classList.toggle("active", n.dataset.section === id);
      });
      if (RENDERERS[id]) RENDERERS[id](content);
    }

    NAV_ITEMS.forEach(function (item) {
      var nav = h("div", "settings-nav-item" + (item.id === active ? " active" : ""));
      nav.dataset.section = item.id;
      nav.appendChild(h("span", "settings-nav-icon", item.icon));
      nav.appendChild(h("span", "settings-nav-label", item.label));
      nav.addEventListener("click", function () { render(this.dataset.section); });
      sidebar.appendChild(nav);
    });

    layout.appendChild(sidebar);
    layout.appendChild(content);
    panel.appendChild(layout);

    overlayEl.appendChild(panel);
    overlayEl.addEventListener("click", function (e) { if (e.target === overlayEl) hide(); });
    document.body.appendChild(overlayEl);

    render("general");
  }

  function hide() {
    if (overlayEl) { overlayEl.remove(); overlayEl = null; }
  }

  // Apply settings on load
  load();
  setTimeout(applyAll, 0);

  return { show: show, hide: hide, get: get, set: set };
})();
