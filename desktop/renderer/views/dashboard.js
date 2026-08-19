"use strict";

window.Views = window.Views || {};

window.Views.dashboard = {
  async render(container, _params) {
    const { el, card, statusDot } = window.ui;

    function stat(label, value, sub) {
      const wrap = el("div", "stat");
      wrap.appendChild(el("div", "stat-label", label));
      wrap.appendChild(el("div", "stat-value", value));
      if (sub) wrap.appendChild(el("div", "stat-sub", sub));
      return wrap;
    }

    const data = await window.api.get("/dashboard");

    // INTERNET
    const internet = card("Internet");
    const grid = el("div", "stat-grid");
    grid.appendChild(stat(
      "Internet",
      data.internet.status === "online" ? "Online" : "Offline",
      `${data.internet.latency_ms ?? "-"} ms latency`
    ));
    grid.appendChild(stat("Public IP", data.internet.public_ip || "-"));
    grid.appendChild(stat("Services",
      [data.services.cloudflare.status, data.services.railway.status, data.services.github.status]
        .map((s) => s === "ok" ? "●" : "○").join(" "),
      "CF · RW · GH"
    ));
    internet._setBody(grid);

    // PROVIDERS
    const providers = card("Providers");
    const pGrid = el("div", "card-grid");
    Object.entries(data.providers || {}).forEach(([key, p]) => {
      const pc = el("div", "provider-card");
      const head = el("div", "head");
      head.appendChild(el("h3", null, p.display_name || key));
      head.appendChild(statusDot(p.status));
      pc.appendChild(head);
      const meta = el("div", "meta");
      meta.textContent = p.panel_url || p.repository_url || "not configured";
      pc.appendChild(meta);
      pGrid.appendChild(pc);
    });
    providers._setBody(pGrid);

    // CONFIGS
    const cfg = card("Configurations");
    const cGrid = el("div", "stat-grid");
    cGrid.appendChild(stat("Total", data.configs.total));
    cGrid.appendChild(stat("Working", data.configs.working, "last tested: " + (data.configs.last_tested || "-")));
    cGrid.appendChild(stat("Failed", data.configs.failed));
    cGrid.appendChild(stat("Degraded", data.configs.degraded));
    cfg._setBody(cGrid);

    // XRAY
    const xray = card("Xray");
    const xGrid = el("div", "stat-grid");
    xGrid.appendChild(stat("Installed", data.xray.installed ? "Yes" : "No", data.xray.path || ""));
    xGrid.appendChild(stat("Status", data.xray.running ? "Running" : "Stopped"));
    xGrid.appendChild(stat("Version", data.xray.version || "-"));
    xray._setBody(xGrid);

    // CLIENTS
    const clients = card("Clients");
    const clGrid = el("div", "stat-grid");
    data.clients.forEach((c) => {
      clGrid.appendChild(stat(c.name, c.detected ? "Detected" : "Not found", c.path || ""));
    });
    clients._setBody(clGrid);

    // SERVICE REGISTRY summary
    const cards = [internet, providers, cfg, xray, clients];
    try {
      const svc = await window.api.get("/services");
      const counts = {};
      (svc.services || []).forEach((s) => {
        const st = (s.status && s.status.status) || "unknown";
        counts[st] = (counts[st] || 0) + 1;
      });
      const registry = card("Service Registry");
      const rGrid = el("div", "stat-grid");
      rGrid.appendChild(stat("Registered", Object.values(counts).reduce((a, b) => a + b, 0)));
      rGrid.appendChild(stat("Ready", counts.ok || 0, "configured / ok"));
      rGrid.appendChild(stat("Needs setup", (counts["not-configured"] || 0) + (counts["not-installed"] || 0)));
      rGrid.appendChild(stat("Errors", counts.error || 0));
      registry._setBody(rGrid);
      cards.push(registry);
    } catch (_) { /* registry may be unavailable */ }

    // NETWORK CHECKER
    try {
      const meta = await window.api.get("/checker/metadata");
      const toolNames = {
        domain_check: "Domain Check", dns_latency: "DNS Latency", dns_hunter: "DNS Hunter",
        edge_ip: "Edge IP", akamai: "Akamai", xray_scan: "Xray Scan",
        sni_spoof_check: "SNI Spoof Check", cloudflare_fix: "Cloudflare Fix", chain: "Chain",
      };
      const tools = Object.entries(meta.defaults || {}).filter(([k]) => toolNames[k]).length;
      let appStatus = "not running";
      let appOk = "muted";
      try {
        const st = await window.jpnh.networkChecker.status();
        if (st && st.running) { appStatus = "running"; appOk = "ok"; }
      } catch (_) { /* launcher unavailable */ }
      const checker = card("Network Checker");
      const chGrid = el("div", "stat-grid");
      chGrid.appendChild(stat("Tools", tools, "native /checker/* API"));
      chGrid.appendChild(stat("Bundled app", appStatus, appOk === "ok" ? "" : "launch from checker page"));
      const openBtn = el("button", "btn small", "Open Network Checker →");
      openBtn.addEventListener("click", () => window.navigate("checker"));
      chGrid.appendChild(openBtn);
      checker._setBody(chGrid);
      cards.push(checker);
    } catch (_) { /* checker API may be unavailable */ }

    container.replaceChildren(...cards);
  },
};