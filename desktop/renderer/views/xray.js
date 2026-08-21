"use strict";

window.Views = window.Views || {};

window.Views.xray = {
  async render(container) {
    const { el, card, badge, statusDot, toast, field } = window.ui;
    const status = await window.api.get("/xray/status");

    const mainCard = card("Xray");
    const statGrid = el("div", "stat-grid");
    const stat = (label, value, sub) => {
      const s = el("div", "stat");
      s.appendChild(el("div", "stat-label", label));
      s.appendChild(el("div", "stat-value", value));
      if (sub) s.appendChild(el("div", "stat-sub", sub));
      return s;
    };
    if (window.JpnhIcons) {
      const xLogo = el("div", "row mb");
      const xBrand = el("span", "brand-logo");
      xBrand.innerHTML = window.JpnhIcons.brandImg("xray", 36);
      xLogo.appendChild(xBrand);
      statGrid.appendChild(xLogo);
    }
    statGrid.appendChild(stat("Installed", status.installed ? "Yes" : "No"));
    statGrid.appendChild(stat("Status", status.running ? "Running" : "Stopped"));
    statGrid.appendChild(stat("Version", status.version || "-"));
    statGrid.appendChild(stat("Path", status.path || "not found", status.path ? "" : "Optional runtime"));

    const actions = el("div", "row mt");
    const mkBtn = (label, kind, fn) => {
      const b = el("button", `btn ${kind}`, label);
      b.disabled = !status.installed;
      b.addEventListener("click", async () => {
        try {
          const r = await window.api.post(`/xray/${label.toLowerCase()}`);
          toast(JSON.stringify(r), r.ok || r.action ? "ok" : "warn");
          window.refreshAll();
        } catch (err) { toast(err.message, "bad"); }
      });
      actions.appendChild(b);
    };
    mkBtn("Start", "primary", null);
    mkBtn("Stop", "danger", null);
    mkBtn("Restart", "", null);
    statGrid.appendChild(actions);
    mainCard._setBody(statGrid);

    // Validate config
    const validateCard = card("Validate Config");
    const cfgInput = el("input", "mono");
    cfgInput.placeholder = "Path to xray config.json";
    const valBtn = el("button", "btn", "Validate");
    const valResult = el("div", "mt");
    valBtn.addEventListener("click", async () => {
      if (!cfgInput.value.trim()) return toast("Enter a config path", "warn");
      valResult.replaceChildren(window.ui.spinner());
      try {
        const r = await window.api.post("/xray/validate", { config_path: cfgInput.value.trim() });
        const statusLabel = r.valid ? "VALID" : "INVALID";
        valResult.replaceChildren(
          el("div", "status-line", [badge(statusLabel, r.valid ? "ok" : "bad"), el("span", "mono", r.error || r.output || "")])
        );
      } catch (err) {
        valResult.replaceChildren(el("div", "bad", err.message));
      }
    });
    validateCard._setBody([field("Config path", cfgInput), valBtn, valResult]);

    container.replaceChildren(mainCard, validateCard);
  },
};
