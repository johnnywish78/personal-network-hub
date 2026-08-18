"use strict";

window.Views = window.Views || {};

window.Views.network = {
  async render(container) {
    const { el, card, badge, statusDot, toast, openModal, closeModal, field } = window.ui;

    // Top actions
    const actionBar = el("div", "row mb");
    const runAll = el("button", "btn primary", "Run Full Diagnostics");
    runAll.addEventListener("click", async () => {
      runAll.disabled = true;
      runAll.textContent = "Running…";
      try {
        const data = await window.api.get("/network/lab");
        showResults(container, data);
      } catch (err) {
        toast(err.message, "bad");
      } finally {
        runAll.disabled = false;
        runAll.textContent = "Run Full Diagnostics";
      }
    });
    actionBar.appendChild(runAll);

    const pingBtn = el("button", "btn", "Latency Matrix");
    pingBtn.addEventListener("click", async () => {
      const data = await window.api.get("/network/latency");
      showResults(container, { latency: data.results });
    });
    actionBar.appendChild(pingBtn);

    const dnsBtn = el("button", "btn", "DNS Latency");
    dnsBtn.addEventListener("click", async () => {
      const data = await window.api.get("/network/dns");
      showResults(container, { dns: data.results });
    });
    actionBar.appendChild(dnsBtn);

    container.replaceChildren(actionBar);

    // Individual tools
    const tools = el("div", "card-grid");
    tools.appendChild(toolCard("Domain Check", ["host"], async (v) => {
      const r = await window.api.post("/network/domain", { host: v.host, port: 443 });
      return renderSingle(r);
    }, (v) => v.host ? null : "Host is required."));
    tools.appendChild(toolCard("TCP Check", ["host", "port"], async (v) => {
      const r = await window.api.post("/network/tcp", { host: v.host, port: v.port });
      return renderSingle(r);
    }, (v) => {
      if (!v.host) return "Host is required.";
      const port = Number(v.port);
      if (!v.port || !Number.isInteger(port) || port < 1 || port > 65535) return "A valid port (1-65535) is required.";
      return null;
    }));
    tools.appendChild(toolCard("TLS Check", ["host"], async (v) => {
      const r = await window.api.post("/network/tls", { host: v.host, port: 443 });
      return renderSingle(r);
    }, (v) => v.host ? null : "Host is required."));
    tools.appendChild(toolCard("DNS Query", ["host", "resolver"], async (v) => {
      const r = await window.api.post("/network/dns/query", { host: v.host, resolver: v.resolver || "system" });
      return renderDns(r);
    }, (v) => v.host ? null : "Host is required."));
    tools.appendChild(toolCard("Clean IP Test", ["address", "ports"], async (v) => {
      const r = await window.api.post("/network/clean-ip", {
        address: v.address,
        ports: v.ports ? v.ports.split(",").map((s) => Number(s.trim())) : null,
      });
      const rows = r.results.map((x) => [
        `${x.address}:${x.port}`,
        badge(x.reachable ? "OPEN" : "CLOSED", x.reachable ? "ok" : "bad"),
        x.latency_ms != null ? `${x.latency_ms} ms` : "-",
        x.error || "-",
      ]);
      return window.ui.table(["Target", "Status", "Latency", "Error"], rows);
    }, (v) => {
      if (!v.address) return "Address is required.";
      if (v.ports) {
        const invalid = v.ports.split(",").some((s) => {
          const p = Number(s.trim());
          return !s.trim() || !Number.isInteger(p) || p < 1 || p > 65535;
        });
        if (invalid) return "Ports must be a comma-separated list of valid ports (1-65535).";
      }
      return null;
    }));
    container.appendChild(tools);
  },
};

function toolCard(title, fields, onRun, validateFn) {
  const { el, card, field, toast, spinner } = window.ui;
  const inputs = {};
  const form = el("div");
  fields.forEach((f) => {
    const input = el("input");
    if (f === "port") input.value = "443";
    if (f === "resolver") input.value = "system";
    input.placeholder = f === "ports" ? "443,2053,2086" : f;
    inputs[f] = input;
    form.appendChild(field(f, input));
  });
  const resultBox = el("div", "mt");
  const btn = el("button", "btn", "Run");
  btn.addEventListener("click", async () => {
    const values = {};
    fields.forEach((f) => (values[f] = inputs[f].value.trim()));
    if (validateFn) {
      const error = validateFn(values);
      if (error) {
        toast(error, "bad");
        resultBox.replaceChildren();
        return;
      }
    }
    resultBox.replaceChildren(spinner());
    try {
      const node = await onRun(values);
      resultBox.replaceChildren(node);
    } catch (err) {
      resultBox.replaceChildren(el("div", "empty", err.message));
    }
  });
  form.appendChild(btn);
  return card(title, [form, resultBox]);
}

function renderSingle(r) {
  const { el, badge, statusDot } = window.ui;
  const wrap = el("div");
  const status = r.reachable === false || r.status === "fail" || r.tls_ok === false ? "FAIL"
    : r.status === "partial" ? "PARTIAL" : "PASS";
  wrap.appendChild(el("div", "status-line", [
    statusDot(status),
    badge(status, status),
    el("span", "muted", r.timestamp || ""),
  ]));
  const kv = el("dl", "kv");
  kv.appendChild(el("dt", null, "Latency"));
  kv.appendChild(el("dd", null, r.latency_ms != null ? `${r.latency_ms} ms` : "-"));
  kv.appendChild(el("dt", null, "Error"));
  kv.appendChild(el("dd", null, r.error || "none"));
  if (r.version) {
    kv.appendChild(el("dt", null, "TLS"));
    kv.appendChild(el("dd", null, r.version));
  }
  wrap.appendChild(kv);
  return wrap;
}

function renderDns(r) {
  const { el, badge } = window.ui;
  const wrap = el("div");
  const status = r.status === "ok" ? "PASS" : r.status === "timeout" ? "TIMEOUT" : "FAIL";
  wrap.appendChild(el("div", "status-line", [
    badge(status, status),
    el("span", "muted", r.resolver),
  ]));
  const kv = el("dl", "kv");
  kv.appendChild(el("dt", null, "Host"));
  kv.appendChild(el("dd", null, r.host));
  kv.appendChild(el("dt", null, "Latency"));
  kv.appendChild(el("dd", null, r.latency_ms != null ? `${r.latency_ms} ms` : "-"));
  kv.appendChild(el("dt", null, "Records"));
  kv.appendChild(el("dd", null, (r.ips || []).join(", ") || "none"));
  if (r.error) {
    kv.appendChild(el("dt", null, "Error"));
    kv.appendChild(el("dd", null, r.error));
  }
  wrap.appendChild(kv);
  return wrap;
}

function showResults(container, data) {
  const { el, card, badge } = window.ui;
  const resultsCard = card("Diagnostics Results");
  const body = el("div");

  const renderEntry = (label, r) => {
    const status = r && r.status ? String(r.status).toUpperCase() : "UNKNOWN";
    const line = el("div", "status-line");
    line.appendChild(el("span", "status-label", label));
    line.appendChild(badge(status, status));
    if (r && r.latency_ms != null) line.appendChild(el("span", "mono", `${r.latency_ms} ms`));
    if (r && r.error) line.appendChild(el("span", "bad", r.error));
    if (r && r.timestamp) line.appendChild(el("span", "muted", r.timestamp.slice(11, 19)));
    body.appendChild(line);
  };

  // Internet
  if (data.internet) renderEntry("Internet", { ...data.internet, status: data.internet.status });
  // DNS latency list
  if (data.dns_cloudflare) renderEntry("DNS 1.1.1.1", data.dns_cloudflare);
  if (data.dns_google) renderEntry("DNS 8.8.8.8", data.dns_google);
  if (data.latency_1_1_1_1) renderEntry("Latency 1.1.1.1", { ...data.latency_1_1_1_1, status: data.latency_1_1_1_1.status });
  if (data.latency_8_8_8_8) renderEntry("Latency 8.8.8.8", { ...data.latency_8_8_8_8, status: data.latency_8_8_8_8.status });
  if (data.github) renderEntry("github.com:443", { ...data.github, status: data.github.status });
  if (data.cloudflare_com) renderEntry("cloudflare.com:443", { ...data.cloudflare_com, status: data.cloudflare_com.status });

  // Standalone views
  if (data.dns) {
    data.dns.forEach((r) => renderEntry(`DNS ${r.host} @${r.resolver}`, r));
  }
  if (data.latency) {
    Object.entries(data.latency).forEach(([host, r]) => renderEntry(`Ping ${host}`, r));
  }

  resultsCard._setBody(body);
  container.appendChild(resultsCard);
}
