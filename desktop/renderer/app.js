"use strict";

(function () {
  const NAV = [
    { id: "dashboard", label: "Dashboard", icon: "dashboard" },
    { id: "browser", label: "Browser", icon: "browser" },
    { id: "services", label: "Services", icon: "services" },
    { id: "checker", label: "Network Checker", icon: "checker" },
    { id: "network", label: "Network", icon: "network" },
    { id: "configs", label: "Configs", icon: "configs" },
    { id: "xray", label: "Xray", icon: "xray" },
    { id: "updates", label: "Updates", icon: "updates" },
    { id: "clients", label: "Clients", icon: "clients" },
    { id: "settings", label: "Settings", icon: "settings" },
  ];

  let current = "dashboard";

  function buildNav() {
    const nav = document.getElementById("nav");
    NAV.forEach((item) => {
      const btn = window.ui.el("button", "nav-item");
      btn.dataset.view = item.id;
      let iconHtml;
      if (item.id === "xray") {
        iconHtml = window.JpnhIcons
          ? `<img src="assets/icons/xray.png" width="22" height="22" alt="Xray" style="object-fit:contain" />`
          : "";
      } else {
        iconHtml = window.JpnhIcons ? window.JpnhIcons.navIcon(item.icon, 22) : "";
      }
      btn.innerHTML = `<span class="nav-icon">${iconHtml}</span><span>${item.label}</span>`;
      btn.addEventListener("click", () => navigate(item.id));
      nav.appendChild(btn);
    });
  }

  async function navigate(viewId, params) {
    const view = window.Views && window.Views[viewId];
    if (!view || !view.render) {
      window.ui.toast(`View "${viewId}" is not available yet`, "warn");
      return;
    }
    current = viewId;
    document.querySelectorAll(".nav-item").forEach((b) => {
      b.classList.toggle("active", b.dataset.view === viewId);
    });
    const titleMap = Object.fromEntries(NAV.map((n) => [n.id, n.label]));
    document.getElementById("view-title").textContent = titleMap[viewId] || viewId;
    const container = document.getElementById("view");
    container.replaceChildren(window.ui.el("div", "empty", "Loading…"));
    try {
      await view.render(container, params || {});
    } catch (err) {
      container.replaceChildren();
      window.ui.toast(`Failed to load ${viewId}: ${err.message}`, "bad");
    }
  }

  async function refreshAll() {
    const view = window.Views && window.Views[current];
    if (view && view.render) {
      await view.render(document.getElementById("view"), { refresh: true });
    }
  }

  function setBackendStatus(online) {
    const el = document.getElementById("backend-status");
    el.textContent = online ? "backend: connected" : "backend: offline";
    el.className = "sidebar-status " + (online ? "ok" : "bad");
  }

  async function checkBackend() {
    try {
      const r = await window.api.get("/ping");
      setBackendStatus(r && r.pong === true);
    } catch (_) {
      setBackendStatus(false);
    }
  }

  // ---- Log viewer ----
  let logLevel = "";

  // ---- First-run wizard (skippable) ----
  async function maybeShowWizard() {
    try {
      const status = await window.api.get("/setup/status");
      if (!status.wizard_required) return;
      showWizard();
    } catch (_) { /* backend offline: skip silently */ }
  }

  function showWizard() {
    const { el, field } = window.ui;
    const overlay = el("div", "wizard-overlay");
    const box = el("div", "wizard");

    const closeWizard = () => overlay.remove();

    const screen = (title, desc) => {
      box.replaceChildren();
      box.appendChild(el("h2", "wizard-title", title));
      if (desc) box.appendChild(el("p", "muted", desc));
      return box;
    };

    const skipBtn = () => {
      const b = el("button", "btn ghost", "Skip");
      b.addEventListener("click", () => {
        window.api.post("/setup/complete", { skipped: true }).then(closeWizard);
      });
      return b;
    };

    const footer = (buttons) => {
      const f = el("div", "row");
      f.style.marginTop = "16px";
      buttons.forEach((b) => f.appendChild(b));
      box.appendChild(f);
    };

    const showWelcome = () => {
      screen("Welcome to Johnny Network Hub",
        "Your private control center for providers, configs, and the embedded browser.");
      const start = el("button", "btn primary", "Get Started");
      start.addEventListener("click", showConnect);
      footer([skipBtn(), start]);
    };

    const showConnect = () => {
      const body = screen("Connect your accounts (optional)",
        "Add API tokens now or later from the Services page. Tokens are stored locally in your secure vault.");
      const gh = el("input", "mono"); gh.type = "password"; gh.placeholder = "GitHub token";
      const cf = el("input", "mono"); cf.type = "password"; cf.placeholder = "Cloudflare token";
      const rw = el("input", "mono"); rw.type = "password"; rw.placeholder = "Railway token";
      body.appendChild(field("GitHub", gh));
      body.appendChild(field("Cloudflare", cf));
      body.appendChild(field("Railway", rw));

      const finish = el("button", "btn primary", "Finish");
      finish.addEventListener("click", async () => {
        try {
          if (gh.value.trim()) await window.api.post("/github/auth", { token: gh.value.trim() });
          if (cf.value.trim()) await window.api.post("/cloudflare/auth", { token: cf.value.trim() });
          if (rw.value.trim()) await window.api.post("/railway/auth", { token: rw.value.trim() });
        } catch (_) { /* non-fatal: tokens may be invalid, still finish */ }
        await window.api.post("/setup/complete", { skipped: false });
        closeWizard();
        window.ui.toast("Setup complete", "ok");
        window.refreshAll();
      });
      footer([skipBtn(), finish]);
    };

    overlay.appendChild(box);
    document.body.appendChild(overlay);
    showWelcome();
  }

  async function openLogs() {
    const modal = document.getElementById("log-modal");
    modal.classList.remove("hidden");
    await loadLogs();
  }

  async function loadLogs() {
    const content = document.getElementById("log-content");
    content.innerHTML = '<span class="spinner"></span>';
    try {
      const data = await window.api.get(`/logs${logLevel ? `?level=${logLevel}` : ""}`);
      content.replaceChildren();
      data.logs.forEach((entry) => {
        const line = window.ui.el(
          "div",
          entry.level,
          `[${entry.timestamp}] ${entry.level.padEnd(7)} ${entry.source}: ${entry.message}`
        );
        content.appendChild(line);
      });
      if (!data.logs.length) content.appendChild(window.ui.el("div", "empty", "No log entries."));
    } catch (err) {
      content.replaceChildren();
      content.appendChild(window.ui.el("div", "empty", `Failed to load logs: ${err.message}`));
    }
  }

  // ---- Sidebar uptime (backend process uptime) ----
  function formatUptime(sec) {
    sec = Math.max(0, Math.floor(sec));
    const d = Math.floor(sec / 86400);
    const h = Math.floor((sec % 86400) / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    const parts = [];
    if (d) parts.push(d + "d");
    if (h) parts.push(h + "h");
    if (m) parts.push(m + "m");
    parts.push(s + "s");
    return parts.join(" ");
  }

  async function updateUptime() {
    const el = document.getElementById("uptime");
    if (!el) return;
    try {
      const r = await window.api.get("/uptime");
      el.textContent = "uptime: " + formatUptime(r.uptime_seconds);
    } catch (_) {
      el.textContent = "uptime: --";
    }
  }

  // ---- Top-center clock ----
  function updateClock() {
    const now = new Date();
    const weekday = document.getElementById("clock-weekday");
    const date = document.getElementById("clock-date");
    const time = document.getElementById("clock-time");
    if (weekday) weekday.textContent = now.toLocaleDateString("en-US", { weekday: "long" });
    if (date) date.textContent = now.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
    if (time) time.textContent = now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  // ---- Theme toggle ----
  function updateThemeBtn() {
    const btn = document.getElementById("btn-theme");
    if (!btn) return;
    const theme = window.Theme ? window.Theme.getTheme() : "dark";
    if (window.JpnhIcons) {
      btn.innerHTML = theme === "dark" ? window.JpnhIcons.utility.sun : window.JpnhIcons.utility.moon;
    } else {
      btn.textContent = theme === "dark" ? "\u2600" : "\u263E";
    }
    btn.title = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
  }

  // ---- Refresh button icon ----
  function renderRefreshBtn() {
    const btn = document.getElementById("btn-refresh");
    if (btn && window.JpnhIcons) {
      btn.innerHTML = window.JpnhIcons.utility.refresh;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    buildNav();
    renderRefreshBtn();
    window.api.init().then(() => {
      checkBackend();
      navigate("dashboard");
      maybeShowWizard();
      updateUptime();
      setInterval(updateUptime, 5000);
    });

    // Top-center clock
    updateClock();
    setInterval(updateClock, 1000);

    // Theme toggle
    updateThemeBtn();
    if (window.Theme) {
      window.Theme.onChange((m) => {
        updateThemeBtn();
        // Sync with browser settings
        if (window.BrowserSettings) window.BrowserSettings.set("theme", m);
      });
    }
    document.getElementById("btn-theme").addEventListener("click", () => {
      if (!window.Theme) return;
      const current = window.Theme.getTheme();
      window.Theme.setMode(current === "dark" ? "light" : "dark");
    });

    document.getElementById("btn-refresh").addEventListener("click", refreshAll);
    document.getElementById("btn-logs").addEventListener("click", openLogs);
    document.getElementById("btn-log-close").addEventListener("click", () => {
      document.getElementById("log-modal").classList.add("hidden");
    });
    document.getElementById("log-modal").addEventListener("click", (e) => {
      if (e.target.id === "log-modal") e.target.classList.add("hidden");
    });
    document.getElementById("btn-log-clear").addEventListener("click", async () => {
      await window.api.del("/logs");
      await loadLogs();
    });
    document.getElementById("btn-log-export").addEventListener("click", async () => {
      const data = await window.api.get("/logs/export");
      await window.ui.copyText(data.content);
      window.ui.toast("Diagnostic log copied to clipboard", "ok");
    });
    document.querySelectorAll("#log-filters .btn.chip").forEach((btn) => {
      btn.addEventListener("click", async () => {
        document.querySelectorAll("#log-filters .btn.chip").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        logLevel = btn.dataset.level || "";
        await loadLogs();
      });
    });
  });

  // Expose to other views
  window.navigate = navigate;
  window.refreshAll = refreshAll;
})();
