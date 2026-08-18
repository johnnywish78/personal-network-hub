"use strict";

window.Views = window.Views || {};

window.Views.configs = {
  async render(container) {
    const { el, card, badge, statusDot, toast, confirmDialog } = window.ui;

    // Import section
    const importCard = card("Import");
    const ta = el("textarea");
    ta.placeholder = "Paste share links (vless://, trojan://, vmess://, ss://), a subscription URL, or JSON config…";
    const row = el("div", "row");
    const providerInput = el("input");
    providerInput.placeholder = "Provider (optional)";
    row.appendChild(providerInput);

    const importBtn = el("button", "btn primary", "Import & Save");
    importBtn.addEventListener("click", async () => {
      if (!ta.value.trim()) return toast("Paste something first", "warn");
      importBtn.disabled = true;
      try {
        const r = await window.api.post("/configs/import", { payload: ta.value, provider: providerInput.value.trim() || null });
        toast(`Imported ${r.imported.length} config(s)${r.already_present ? `, ${r.already_present} already present` : ""}`, r.imported.length ? "ok" : "warn");
        ta.value = "";
        window.refreshAll();
      } catch (err) { toast(err.message, "bad"); }
      finally { importBtn.disabled = false; }
    });
    row.appendChild(importBtn);

    const parseBtn = el("button", "btn", "Parse (preview)");
    parseBtn.addEventListener("click", async () => {
      if (!ta.value.trim()) return toast("Paste something first", "warn");
      try {
        const r = await window.api.post("/configs/parse", { payload: ta.value });
        showParsePreview(r);
      } catch (err) { toast(err.message, "bad"); }
    });
    row.appendChild(parseBtn);

    importCard._setBody([ta, row]);
    container.replaceChildren(importCard);

    // Config list
    const data = await window.api.get("/configs");
    const counts = data.counts || {};
    const listCard = card("Saved Configurations", el("div", "muted",
      `total ${counts.total} · working ${counts.working} · degraded ${counts.degraded} · failed ${counts.failed}`));

    if (!data.configs.length) {
      listCard._setBody(el("div", "empty", "No saved configurations yet. Import one above."));
      container.appendChild(listCard);
      return;
    }

    const body = el("div");
    const retestAll = el("button", "btn", "Retest All");
    retestAll.addEventListener("click", async () => {
      retestAll.disabled = true;
      retestAll.textContent = "Testing…";
      const ids = data.configs.map((c) => c.id);
      try {
        const r = await window.api.post("/configs/test", ids);
        toast(`Tested ${r.results.length} config(s)`, "ok");
        window.refreshAll();
      } catch (err) { toast(err.message, "bad"); }
      finally { retestAll.disabled = false; retestAll.textContent = "Retest All"; }
    });
    body.appendChild(retestAll);

    data.configs.forEach((c) => {
      body.appendChild(configRow(c));
    });
    listCard._setBody(body);
    container.appendChild(listCard);
  },
};

function configRow(c) {
  const { el, badge, statusDot, toast, openModal, closeModal, confirmDialog } = window.ui;
  const row = el("div", "config-row");

  const nameCell = el("div");
  nameCell.appendChild(el("div", "name", c.name || "Unnamed"));
  nameCell.appendChild(el("div", "dim", `${c.provider || "unknown provider"} · ${c.protocol || "-"}`));
  row.appendChild(nameCell);

  row.appendChild(el("div", "dim", c.address ? `${c.address}:${c.port}` : "-"));

  const secCell = el("div", "dim");
  secCell.textContent = [c.security, c.network].filter(Boolean).join(" · ") || "-";
  row.appendChild(secCell);

  const statusCell = el("div");
  statusCell.appendChild(el("span", null, [
    statusDot(c.status),
    el("span", null, c.status),
  ]));
  row.appendChild(statusCell);

  row.appendChild(el("div", "mono", c.latency_ms != null ? `${c.latency_ms} ms` : "-"));
  row.appendChild(el("div", "dim", c.last_tested_at ? c.last_tested_at.slice(11, 19) : "never"));

  const actions = el("div", "actions");
  const btn = (label, kind, fn) => {
    const b = el("button", `btn small ${kind || ""}`, label);
    b.addEventListener("click", fn);
    actions.appendChild(b);
  };

  btn("Test", "primary", async () => {
    try {
      const r = await window.api.post(`/configs/${c.id}/test`);
      toast(`${c.name}: ${r.result} (${r.latency_ms ?? "-"} ms)` + (r.error ? ` — ${r.error}` : ""), r.result === "PASS" ? "ok" : "warn");
      window.refreshAll();
    } catch (err) { toast(err.message, "bad"); }
  });

  btn("Copy", "ghost", async () => {
    try {
      const r = await window.api.get(`/configs/${c.id}/uri`);
      await window.ui.copyText(r.uri);
      toast("URI copied to clipboard", "ok");
    } catch (err) { toast(err.message, "bad"); }
  });

  btn("QR", "ghost", async () => {
    try {
      const r = await window.api.get(`/configs/${c.id}/qr`);
      showQr(r);
    } catch (err) { toast(err.message, "bad"); }
  });

  btn("Export", "ghost", async () => {
    try {
      const r = await window.api.get(`/configs/${c.id}/export?fmt=json`);
      await window.ui.copyText(r.content);
      toast("Config JSON copied to clipboard", "ok");
    } catch (err) { toast(err.message, "bad"); }
  });

  btn("Details", "ghost", async () => {
    try {
      const detail = await window.api.get(`/configs/${c.id}`);
      showDetails(detail);
    } catch (err) { toast(err.message, "bad"); }
  });

  btn("Delete", "danger", () => {
    confirmDialog("Delete configuration", `Delete "${c.name}"? This cannot be undone.`, async () => {
      await window.api.del(`/configs/${c.id}`);
      toast("Deleted", "ok");
      window.refreshAll();
    });
  });

  row.appendChild(actions);
  return row;
}

function showDetails(c) {
  const { el, openModal, closeModal, table } = window.ui;
  const rows = Object.entries(c)
    .filter(([k, v]) => v !== null && v !== "" && !["raw_config", "allowed_ips"].includes(k) && !(Array.isArray(v) && !v.length))
    .map(([k, v]) => [k, Array.isArray(v) ? v.join(", ") : String(v)]);
  const t = table(["Field", "Value"], rows);
  const raw = el("details", "mt");
  const summary = el("summary", null, "Raw original config");
  raw.appendChild(summary);
  raw.appendChild(el("pre", "mono", c.raw_config || "(none)"));
  openModal(c.name, [t, raw], [{ label: "Close", kind: "ghost", onClick: (o) => closeModal(o) }]);
}

function showQr(r) {
  const { el, openModal, closeModal, copyText, toast } = window.ui;
  const img = el("img");
  img.src = "data:image/png;base64," + r.png_base64;
  img.style.width = "240px";
  img.style.height = "240px";
  const wrap = el("div", "mt");
  const copyBtn = el("button", "btn small", "Copy URI");
  copyBtn.addEventListener("click", async () => {
    await copyText(r.uri);
    toast("URI copied", "ok");
  });
  wrap.appendChild(copyBtn);
  openModal("QR Code", [img, wrap], [{ label: "Close", kind: "ghost", onClick: (o) => closeModal(o) }]);
}

function showParsePreview(r) {
  const { el, openModal, closeModal, table } = window.ui;
  const rows = (r.results || []).map((item) => {
    if (item.error) return ["-", "-", "-", item.error];
    const p = item.parsed || {};
    return [p.protocol || "-", `${p.address || "-"}:${p.port || "-"}`,
      p.security || "-", item.validation_ok ? "valid" : "invalid"];
  });
  const t = table(["Protocol", "Address", "Security", "Validation"], rows);
  openModal("Parse preview", t, [{ label: "Close", kind: "ghost", onClick: (o) => closeModal(o) }]);
}
