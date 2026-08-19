"use strict";

(function () {
  const NAV = [
    { id: "dashboard", label: "Dashboard", icon: "▦" },
    { id: "browser", label: "Browser", icon: "⟐" },
    { id: "services", label: "Services", icon: "▤" },
    { id: "checker", label: "Network Checker", icon: "◈" },
    { id: "network", label: "Network", icon: "⛨" },
    { id: "configs", label: "Configs", icon: "⚙" },
    { id: "xray", label: "Xray", icon: "◎" },
    { id: "updates", label: "Updates", icon: "⇅" },
    { id: "clients", label: "Clients", icon: "▣" },
    { id: "settings", label: "Settings", icon: "⚑" },
  ];

  let current = "dashboard";

  function buildNav() {
    const nav = document.getElementById("nav");
    NAV.forEach((item) => {
      const btn = window.ui.el("button", "nav-item");
      btn.dataset.view = item.id;
      btn.innerHTML = `<span>${item.icon}</span><span>${item.label}</span>`;
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

  // ---- Topbar clock (date / weekday / time) ----
  function updateClock() {
    const now = new Date();
    const date = document.getElementById("clock-date");
    const weekday = document.getElementById("clock-weekday");
    const time = document.getElementById("clock-time");
    if (!date || !weekday || !time) return;
    weekday.textContent = now.toLocaleDateString(undefined, { weekday: "short" });
    date.textContent = now.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    time.textContent = now.toLocaleTimeString();
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

  // ---- Theme toggle (day / night) ----
  function updateThemeBtn(theme) {
    const btn = document.getElementById("btn-theme");
    if (!btn) return;
    if (theme === "dark") {
      btn.textContent = "☀";
      btn.title = "Switch to light theme";
    } else {
      btn.textContent = "☾";
      btn.title = "Switch to dark theme";
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    buildNav();
    window.api.init().then(() => {
      checkBackend();
      navigate("dashboard");
      maybeShowWizard();
      updateUptime();
      setInterval(updateUptime, 5000);
    });

    updateClock();
    setInterval(updateClock, 1000);
    updateThemeBtn(window.Theme ? window.Theme.getTheme() : "dark");
    window.Theme.onChange((mode) => updateThemeBtn(window.Theme.getTheme()));
    document.getElementById("btn-theme").addEventListener("click", () => {
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
