"use strict";

// Network Checker Hub: every tool from the native /checker/* API, plus the
// bundled Network Checker app launcher. Ports of the GPL-3.0
// mirarr-app/network-checker project.

window.Views = window.Views || {};

function checkerToolCard(title, fields, onRun, { desc } = {}) {
  const { el, card, field, toast, spinner, copyText } = window.ui;
  const inputs = {};
  const form = el("div");
  if (desc) form.appendChild(el("p", "muted", desc));
  fields.forEach((f) => {
    const input = el(f.multiline ? "textarea" : "input");
    if (f.type === "number") input.type = "number";
    if (f.value !== undefined) input.value = f.value;
    if (f.placeholder) input.placeholder = f.placeholder;
    if (f.rows) input.rows = f.rows;
    inputs[f.name] = input;
    form.appendChild(field(f.label, input));
  });
  const resultBox = el("div", "mt");
  const btn = el("button", "btn", "Run");
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Running…";
    resultBox.replaceChildren(spinner());
    const values = {};
    fields.forEach((f) => (values[f.name] = inputs[f.name].value.trim()));
    try {
      const node = await onRun(values);
      resultBox.replaceChildren(node);
      if (node && node._copyText) {
        const copy = el("button", "btn small ghost mt", "Copy output");
        copy.addEventListener("click", () => copyText(node._copyText).then(() => toast("Copied", "ok")));
        resultBox.appendChild(copy);
      }
    } catch (err) {
      resultBox.replaceChildren(el("div", "empty", err.message));
    } finally {
      btn.disabled = false;
      btn.textContent = "Run";
    }
  });
  form.appendChild(btn);
  return card(title, [form, resultBox]);
}

function outputPre(text) {
  const { el } = window.ui;
  const pre = el("pre", "log-view");
  pre.style.height = "220px";
  pre.textContent = text;
  const wrap = el("div");
  wrap.appendChild(pre);
  wrap._copyText = text;
  return wrap;
}

function resultStats(data) {
  const { el } = window.ui;
  const grid = el("div", "stat-grid");
  const stat = (label, value) => {
    const w = el("div", "stat");
    w.appendChild(el("div", "stat-label", label));
    w.appendChild(el("div", "stat-value", value == null ? "-" : String(value)));
    grid.appendChild(w);
  };
  Object.entries(data).forEach(([k, v]) => {
    if (typeof v === "number" || typeof v === "string" || typeof v === "boolean") stat(k, v);
  });
  return grid;
}

window.Views.checker = {
  async render(container, _params) {
    const { el, card, badge, toast, spinner } = window.ui;

    container.replaceChildren(
      el("div", "empty", "Loading Network Checker…"),
      el("div", "spinner")
    );

    let meta;
    try {
      meta = await window.api.get("/checker/metadata");
    } catch (err) {
      toast("Could not load tool metadata: " + err.message, "bad");
      meta = { defaults: {} };
    }
    const d = meta.defaults || {};

    const tools = el("div");

    // --- Diagnostics group ---
    const diagGroup = el("div");
    diagGroup.appendChild(el("h3", "section-title", "Diagnostics"));

    const diagCard = card("Internet Diagnostics", [
      el("p", "muted", "Full battery: DNS, IPv4/IPv6, HTTPS, DNS provider analysis, routing, TLS interception, websites, social media, CDNs."),
    ]);
    const diagBtn = el("button", "btn primary", "Run Full Diagnostics");
    diagBtn.addEventListener("click", async () => {
      diagBtn.disabled = true;
      diagBtn.textContent = "Running…";
      const body = diagCard.lastChild;
      body.replaceChildren(spinner());
      try {
        const data = await window.api.get("/checker/internet-diagnostics");
        body.replaceChildren(renderDiagnostics(data));
      } catch (err) {
        body.replaceChildren(el("div", "empty", err.message));
      } finally {
        diagBtn.disabled = false;
        diagBtn.textContent = "Run Full Diagnostics";
      }
    });
    diagCard.lastChild.appendChild(diagBtn);
    diagGroup.appendChild(diagCard);

    const protoCard = card("Protocol Accessibility", [
      el("p", "muted", "TCP HTTP/HTTPS, UDP, DoH, DoT and ICMP reachability across sample endpoints."),
    ]);
    const protoBtn = el("button", "btn", "Check Protocols");
    protoBtn.addEventListener("click", async () => {
      protoBtn.disabled = true;
      protoBtn.textContent = "Checking…";
      const body = protoCard.lastChild;
      body.replaceChildren(spinner());
      try {
        const data = await window.api.get("/checker/protocols");
        body.replaceChildren(renderProtocols(data));
      } catch (err) {
        body.replaceChildren(el("div", "empty", err.message));
      } finally {
        protoBtn.disabled = false;
        protoBtn.textContent = "Check Protocols";
      }
    });
    protoCard.lastChild.appendChild(protoBtn);
    diagGroup.appendChild(protoCard);
    tools.appendChild(diagGroup);

    // --- Domain / DNS group ---
    const dnsGroup = el("div");
    dnsGroup.appendChild(el("h3", "section-title", "Domains & DNS"));
    dnsGroup.appendChild(checkerToolCard("Domain Check", [
      { name: "targets", label: "Targets (comma/newline separated)", multiline: true, rows: 3, placeholder: "example.com, github.com" },
      { name: "timeout", label: "Timeout (s)", type: "number", value: d.domain_check ? d.domain_check.timeout : 3 },
      { name: "concurrency", label: "Concurrency", type: "number", value: d.domain_check ? d.domain_check.concurrency : 10 },
    ], async (v) => {
      const targets = v.targets ? v.targets.split(/[\s,]+/).filter(Boolean) : null;
      if (!targets || !targets.length) throw new Error("At least one target is required.");
      const r = await window.api.post("/checker/domain-check", {
        targets, timeout: Number(v.timeout), concurrency: Number(v.concurrency),
      });
      return renderDomainResults(r);
    }));

    dnsGroup.appendChild(checkerToolCard("DNS Latency", [
      { name: "providers", label: "Providers (JSON array, optional)", multiline: true, rows: 3, placeholder: '[{"name":"1.1.1.1","address":"1.1.1.1"}]' },
      { name: "timeout", label: "Timeout (s)", type: "number", value: d.dns_latency ? d.dns_latency.timeout : 2 },
      { name: "concurrency", label: "Concurrency", type: "number", value: d.dns_latency ? d.dns_latency.concurrency : 10 },
    ], async (v) => {
      const providers = v.providers ? JSON.parse(v.providers) : null;
      const r = await window.api.post("/checker/dns-latency", {
        providers, timeout: Number(v.timeout), concurrency: Number(v.concurrency),
      });
      return renderDnsLatency(r);
    }));

    dnsGroup.appendChild(checkerToolCard("DNS Hunter", [
      { name: "target", label: "Target", value: "twitter" },
      { name: "custom_domain", label: "Custom domain (optional)" },
      { name: "ranges", label: "Ranges (defaults to all DNS ranges)", multiline: true, rows: 2 },
      { name: "concurrency", label: "Concurrency", type: "number", value: d.dns_hunter ? d.dns_hunter.concurrency : 50 },
      { name: "timeout", label: "Timeout (s)", type: "number", value: d.dns_hunter ? d.dns_hunter.timeout : 2 },
      { name: "max_ips", label: "Max IPs", type: "number", value: d.dns_hunter ? d.dns_hunter.max_ips : 500 },
    ], async (v) => {
      const ranges = v.ranges ? v.ranges.split(/[\s,]+/).filter(Boolean) : null;
      const r = await window.api.post("/checker/dns-hunter", {
        ranges, target: v.target, custom_domain: v.custom_domain,
        concurrency: Number(v.concurrency), timeout: Number(v.timeout), max_ips: Number(v.max_ips),
      });
      return renderHunter(r);
    }));
    tools.appendChild(dnsGroup);

    // --- CDN / IP group ---
    const cdnGroup = el("div");
    cdnGroup.appendChild(el("h3", "section-title", "CDN & IP"));
    cdnGroup.appendChild(checkerToolCard("Edge IP Scan", [
      { name: "ip_input", label: "IPs / ranges (one per line)", multiline: true, rows: 3, placeholder: "1.1.1.1\n8.8.8.0/24" },
      { name: "test_domain", label: "Test domain", value: d.edge_ip ? d.edge_ip.test_domain : "chatgpt.com" },
      { name: "port", label: "Port", type: "number", value: d.edge_ip ? d.edge_ip.port : 443 },
      { name: "timeout", label: "Timeout (s)", type: "number", value: d.edge_ip ? d.edge_ip.timeout : 3 },
      { name: "max_workers", label: "Max workers", type: "number", value: d.edge_ip ? d.edge_ip.max_workers : 20 },
    ], async (v) => {
      if (!v.ip_input) throw new Error("Enter IPs to scan.");
      const r = await window.api.post("/checker/edge-ip", {
        ip_input: v.ip_input, test_domain: v.test_domain, port: Number(v.port),
        timeout: Number(v.timeout), max_workers: Number(v.max_workers), test_download: false,
      });
      return renderEdgeIp(r);
    }));

    cdnGroup.appendChild(checkerToolCard("Akamai Scan", [
      { name: "ip_input", label: "IPs / ranges (one per line)", multiline: true, rows: 3, placeholder: "1.1.1.1\n8.8.8.0/24" },
      { name: "port", label: "Port", type: "number", value: d.akamai ? d.akamai.port : 443 },
      { name: "timeout", label: "Timeout (s)", type: "number", value: d.akamai ? d.akamai.timeout : 2 },
      { name: "max_workers", label: "Max workers", type: "number", value: d.akamai ? d.akamai.max_workers : 100 },
    ], async (v) => {
      if (!v.ip_input) throw new Error("Enter IPs to scan.");
      const r = await window.api.post("/checker/akamai", {
        ip_input: v.ip_input, port: Number(v.port),
        timeout: Number(v.timeout), max_workers: Number(v.max_workers),
      });
      return renderAkamai(r);
    }));

    cdnGroup.appendChild(checkerToolCard("CDN Xray Scan", [
      { name: "ip_input", label: "Candidate IPs / ranges (one per line)", multiline: true, rows: 3, placeholder: "1.1.1.1\n8.8.8.0/24" },
      { name: "config_json", label: "Xray config JSON (vless/vmess/trojan outbound)", multiline: true, rows: 5, placeholder: '{"inbounds":[{"protocol":"socks","port":10808}],"outbounds":[{"protocol":"vless","settings":{"vnext":[{"address":"server","port":443}]}}]}' },
      { name: "concurrency", label: "Concurrency", type: "number", value: d.xray_scan ? d.xray_scan.concurrency : 5 },
      { name: "timeout", label: "Timeout (s)", type: "number", value: d.xray_scan ? d.xray_scan.timeout : 10 },
      { name: "startup_delay", label: "Startup delay (s)", type: "number", value: d.xray_scan ? d.xray_scan.startup_delay : 2 },
      { name: "test_url", label: "Test URL", value: d.xray_scan ? d.xray_scan.test_url : "https://www.google.com/generate_204" },
      { name: "max_ips", label: "Max IPs", type: "number", value: 200 },
    ], async (v) => {
      if (!v.ip_input) throw new Error("Enter candidate IPs to scan.");
      if (!v.config_json) throw new Error("Paste an Xray config JSON.");
      const r = await window.api.post("/checker/xray-scan", {
        ip_input: v.ip_input, config_json: v.config_json,
        concurrency: Number(v.concurrency), timeout: Number(v.timeout),
        startup_delay: Number(v.startup_delay), test_url: v.test_url,
        max_ips: Number(v.max_ips),
      });
      return renderXrayScan(r);
    }));
    tools.appendChild(cdnGroup);

    // --- Config tools group ---
    const cfgGroup = el("div");
    cfgGroup.appendChild(el("h3", "section-title", "Config Tools"));
    cfgGroup.appendChild(checkerToolCard("VLESS Modifier", [
      { name: "configs", label: "VLESS configs (one per line)", multiline: true, rows: 3, placeholder: "vless://uuid@host:443?security=tls&sni=example.com#Node" },
      { name: "ips", label: "IPs to substitute (one per line)", multiline: true, rows: 3 },
    ], async (v) => {
      if (!v.configs || !v.ips) throw new Error("Both configs and IPs are required.");
      const r = await window.api.post("/checker/vless-modify", { configs: v.configs, ips: v.ips, parse_ips: true });
      if (r.error) throw new Error(r.error);
      return outputPre((r.configs || []).join("\n"));
    }));

    cfgGroup.appendChild(checkerToolCard("Netlify Generator", [
      { name: "uuid", label: "UUID" },
      { name: "path", label: "Path" },
      { name: "netlify_domain", label: "Netlify domain" },
      { name: "xhttp_object", label: "XHTTP object" },
      { name: "snis", label: "SNIs (comma separated)" },
      { name: "ips", label: "IPs (comma separated)" },
    ], async (v) => {
      const snis = v.snis.split(",").map((s) => s.trim()).filter(Boolean);
      const ips = v.ips.split(",").map((s) => s.trim()).filter(Boolean);
      if (!v.uuid || !v.path || !v.netlify_domain || !v.xhttp_object || !snis.length || !ips.length) {
        throw new Error("All fields are required.");
      }
      const r = await window.api.post("/checker/netlify-generate", {
        uuid: v.uuid, path: v.path, netlify_domain: v.netlify_domain,
        xhttp_object: v.xhttp_object, snis, ips,
      });
      return outputPre((r.configs || []).join("\n"));
    }));
    tools.appendChild(cfgGroup);

    // --- New native tools group ---
    const nativeGroup = el("div");
    nativeGroup.appendChild(el("h3", "section-title", "SNI & Chain Tools"));

    nativeGroup.appendChild(checkerToolCard("SNI Spoof Check", [
      { name: "targets", label: "Targets (one per line)", multiline: true, rows: 3, placeholder: (d.sni_spoof_check && d.sni_spoof_check.targets || []).join("\n") },
      { name: "ports", label: "Ports (comma separated)", value: (d.sni_spoof_check && d.sni_spoof_check.ports || [443]).join(",") },
      { name: "timeout", label: "Timeout (s)", type: "number", value: d.sni_spoof_check ? d.sni_spoof_check.timeout : 5 },
      { name: "retries", label: "Retries", type: "number", value: d.sni_spoof_check ? d.sni_spoof_check.retries : 3 },
      { name: "concurrency", label: "Concurrency", type: "number", value: d.sni_spoof_check ? d.sni_spoof_check.concurrency : 20 },
      { name: "enable_ip_check", label: "IP check (default off)", value: "" },
      { name: "manual_ip", label: "Manual public IP (optional)" },
    ], async (v) => {
      const targets = v.targets ? v.targets.split(/\s+/).filter(Boolean) : null;
      if (!targets || !targets.length) throw new Error("At least one target is required.");
      const ports = v.ports.split(",").map((s) => Number(s.trim())).filter(Boolean);
      if (!ports.length) throw new Error("At least one port is required.");
      const r = await window.api.post("/checker/sni-spoof-check", {
        targets: targets.join("\n"), ports,
        timeout: Number(v.timeout), retries: Number(v.retries), concurrency: Number(v.concurrency),
        enable_ip_check: false, manual_ip: v.manual_ip,
      });
      return renderSni(r);
    }));

    nativeGroup.appendChild(checkerToolCard("Cloudflare Fix", [
      { name: "links", label: "VLESS links (one per line)", multiline: true, rows: 4, placeholder: "vless://uuid@host:443?security=tls&#8230;" },
      { name: "socks_port", label: "SOCKS port", type: "number", value: d.cloudflare_fix ? d.cloudflare_fix.socks_port || 10808 : 10808 },
      { name: "http_port", label: "HTTP port", type: "number", value: d.cloudflare_fix ? d.cloudflare_fix.http_port || 10809 : 10809 },
      { name: "dns_server", label: "DNS server", value: d.cloudflare_fix ? d.cloudflare_fix.dns_server : "" },
      { name: "remark_suffix", label: "Remark suffix", value: d.cloudflare_fix ? d.cloudflare_fix.remark_suffix || "-custom" : "-custom" },
      { name: "fingerprint", label: "Fingerprint", value: d.cloudflare_fix ? d.cloudflare_fix.fingerprint || "unsafe" : "unsafe" },
    ], async (v) => {
      if (!v.links) throw new Error("Paste one or more VLESS links.");
      const r = await window.api.post("/checker/cloudflare-fix", {
        links: v.links, socks_port: Number(v.socks_port), http_port: Number(v.http_port),
        dns_server: v.dns_server || undefined, remark_suffix: v.remark_suffix,
        fingerprint: v.fingerprint,
      });
      return renderCloudflareFix(r);
    }));

    nativeGroup.appendChild(checkerToolCard("Chain Generator", [
      { name: "links", label: "Proxy links (Entry then Exit)", multiline: true, rows: 4, placeholder: "vless://…\nvmess://…" },
      { name: "socks_port", label: "SOCKS port", type: "number", value: d.chain ? d.chain.socks_port : 10808 },
      { name: "http_port", label: "HTTP port", type: "number", value: d.chain ? d.chain.http_port : 10809 },
    ], async (v) => {
      if (!v.links) throw new Error("Provide at least two proxy links.");
      const r = await window.api.post("/checker/chain", {
        links: v.links, socks_port: Number(v.socks_port), http_port: Number(v.http_port),
      });
      if (r.error) throw new Error(r.error);
      const node = outputPre(r.json || r.profile);
      const head = el("div", "status-line");
      head.appendChild(badge("HOP COUNT: " + r.hop_count, "ok"));
      node.insertBefore(head, node.firstChild);
      return node;
    }));
    tools.appendChild(nativeGroup);

    // --- Bundled app manage ---
    const manage = card("Bundled Network Checker App");
    const manageBody = el("div");
    manageBody.appendChild(el("p", "muted",
      "Launch the original Flutter app bundled with JPNH. It ships all upstream tools, including SMS Encoder (Android-only)."));
    const manageRow = el("div", "row");
    const launch = el("button", "btn primary", "Launch Network Checker");
    launch.addEventListener("click", () => {
      window.jpnh.networkChecker.launch().then((r) => {
        if (r && r.ok) toast("Network Checker launched", "ok");
        else toast((r && r.error) || "Network Checker could not be launched", "bad");
      }).catch((err) => toast(err.message, "bad"));
    });
    const statusBtn = el("button", "btn ghost", "Check status");
    statusBtn.addEventListener("click", async () => {
      statusBtn.disabled = true;
      statusBtn.textContent = "Checking…";
      try {
        const r = await window.jpnh.networkChecker.status();
        toast("Status: " + ((r && r.running) ? "running" : "not running"), "info");
      } catch (err) {
        toast("Status unavailable: " + err.message, "warn");
      } finally {
        statusBtn.disabled = false;
        statusBtn.textContent = "Check status";
      }
    });
    manageRow.appendChild(launch);
    manageRow.appendChild(statusBtn);
    manageBody.appendChild(manageRow);
    manage._setBody(manageBody);
    tools.appendChild(manage);

    container.replaceChildren(tools);
  },
};

// ---- renderers ----

function renderDiagnostics(data) {
  const { el, badge } = window.ui;
  const wrap = el("div");
  const overall = data.overall_internet_access ? "ONLINE" : "OFFLINE";
  wrap.appendChild(el("div", "status-line", [
    badge(overall, overall),
    el("span", "muted", data.name || "Internet Diagnostics"),
  ]));
  const checks = data.checks || {};
  Object.entries(checks).forEach(([key, c]) => {
    if (!c) return;
    const ok = c.success ? "ok" : "bad";
    const line = el("div", "status-line");
    line.appendChild(el("span", "status-label", key.replace(/_/g, " ")));
    line.appendChild(badge(c.success ? "PASS" : "FAIL", ok));
    if (c.latency_ms != null) line.appendChild(el("span", "mono", c.latency_ms + " ms"));
    if (c.message) line.appendChild(el("span", "muted", c.message));
    wrap.appendChild(line);
  });
  return wrap;
}

function renderProtocols(data) {
  const { el, badge, table } = window.ui;
  const wrap = el("div");
  wrap.appendChild(el("div", "status-line", [
    badge((data.supported || 0) + " supported", "ok"),
    badge((data.blocked || 0) + " blocked", "bad"),
  ]));
  const rows = (data.summaries || []).map((s) => [
    s.protocol_name,
    badge(s.is_supported ? "OK" : "BLOCKED", s.is_supported ? "ok" : "bad"),
    (s.results || []).map((r) => r.domain).join(", "),
    s.description || "-",
  ]);
  wrap.appendChild(table(["Protocol", "Status", "Tested", "Description"], rows));
  return wrap;
}

function renderDomainResults(r) {
  const { el, badge, table } = window.ui;
  const rows = (r.results || []).map((x) => [
    x.target,
    badge(x.success ? "OK" : "FAIL", x.success ? "ok" : "bad"),
    x.response_time_ms != null ? x.response_time_ms + " ms" : "-",
    x.status_code != null ? x.status_code : "-",
    x.error || "-",
  ]);
  return table(["Target", "Status", "Latency", "HTTP", "Error"], rows);
}

function renderDnsLatency(r) {
  const { el, badge, table } = window.ui;
  const rows = (r.results || []).map((x) => [
    x.provider_name || "-",
    x.address,
    badge(x.success ? "OK" : "FAIL", x.success ? "ok" : "bad"),
    x.latency_ms != null ? x.latency_ms + " ms" : "-",
    x.error || "-",
  ]);
  return table(["Provider", "Server", "Status", "Latency", "Error"], rows);
}

function renderHunter(r) {
  const { el, badge, table } = window.ui;
  const wrap = el("div");
  wrap.appendChild(resultStats({
    target: r.target, scanned: r.scanned, clean: r.clean, total_ranges: r.total_ranges,
  }));
  const rows = (r.results || []).map((x) => [
    x.ip || x.domain || x.address || "-",
    x.latency_ms != null ? x.latency_ms + " ms" : "-",
    x.is_clean ? badge("CLEAN", "ok") : badge("USED", "warn"),
    x.error || "-",
  ]);
  if (rows.length) wrap.appendChild(table(["IP", "Latency", "Status", "Error"], rows));
  return wrap;
}

function renderEdgeIp(r) {
  const { el, badge, table } = window.ui;
  const wrap = el("div");
  wrap.appendChild(resultStats({ total: r.total, scanned: r.scanned, successful: r.successful }));
  const rows = (r.results || []).map((x) => [
    x.ip,
    x.port,
    badge(x.success ? "OK" : "FAIL", x.success ? "ok" : "bad"),
    x.latency_ms != null ? x.latency_ms + " ms" : "-",
    x.error || "-",
  ]);
  if (rows.length) wrap.appendChild(table(["IP", "Port", "Status", "Latency", "Error"], rows));
  return wrap;
}

function renderAkamai(r) {
  const { el, badge, table } = window.ui;
  const wrap = el("div");
  wrap.appendChild(resultStats({ total: r.total, open: r.open }));
  const rows = (r.results || []).map((x) => [
    x.ip,
    x.port,
    badge(x.is_open ? "OPEN" : "CLOSED", x.is_open ? "ok" : "bad"),
    x.latency_ms != null ? x.latency_ms + " ms" : "-",
    x.error || "-",
  ]);
  if (rows.length) wrap.appendChild(table(["IP", "Port", "Status", "Latency", "Error"], rows));
  return wrap;
}

function renderSni(r) {
  const { el, badge, table } = window.ui;
  const wrap = el("div");
  const status = r.ok > 0 ? "ok" : "bad";
  wrap.appendChild(el("div", "status-line", [
    badge("OK " + (r.ok || 0), "ok"),
    badge("FAIL " + (r.fail || 0), "bad"),
    badge("FILTERED " + (r.filtered || 0), "warn"),
    el("span", "muted", "public IP: " + (r.user_public_ip || "-")),
  ]));
  const rows = (r.results || []).map((x) => {
    const ports = (x.port_results || []).map((p) => p.port).join(", ");
    return [x.target, x.ip || "-", badge(x.status || "?", x.status), ports, x.error || "-"];
  });
  if (rows.length) wrap.appendChild(table(["Target", "IP", "Status", "Ports", "Error"], rows));
  return wrap;
}

function renderCloudflareFix(r) {
  const { el, badge, table } = window.ui;
  const wrap = el("div");
  if ((r.errors || []).length) {
    wrap.appendChild(el("div", "status-line", [
      badge("ERRORS " + r.errors.length, "bad"),
    ]));
    r.errors.forEach((e) => wrap.appendChild(el("div", "muted mono", e.link + " → " + e.error)));
  }
  if ((r.results || []).length) {
    const rows = r.results.map((x) => [
      x.remarks || "-",
      x.address + ":" + x.port,
      x.network || "-",
      x.fingerprint || "-",
      (x.alpn || []).join(",") || "-",
    ]);
    wrap.appendChild(table(["Remarks", "Address", "Network", "Fingerprint", "ALPN"], rows));
    const all = r.results.map((x) => x.formatted_json || x.json_config).join("\n\n");
    wrap.appendChild(outputPre(all));
  }
  return wrap;
}

function renderXrayScan(r) {
  const { el, badge, table } = window.ui;
  const wrap = el("div");
  wrap.appendChild(el("div", "status-line", [
    badge("WORKING " + (r.successful || 0), "ok"),
    el("span", "muted", "test: " + (r.test_url || "-")),
  ]));
  const rows = (r.results || []).map((x) => [
    x.ip,
    badge(x.success ? "OK" : "FAIL", x.success ? "ok" : "bad"),
    x.latency_ms != null ? x.latency_ms + " ms" : "-",
    x.error || "-",
  ]);
  if (rows.length) wrap.appendChild(table(["IP", "Status", "Latency", "Error"], rows));
  if (r.working_ips && r.working_ips.length) {
    const ips = (r.working_ips || []).map((x) => x.ip).join("\n");
    wrap.appendChild(outputPre(ips));
  }
  return wrap;
}