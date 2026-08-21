"use strict";

window.Views = window.Views || {};

window.Views.providers = {
  async render(container) {
    const { el, card, badge, toast, openModal, closeModal, field } = window.ui;
    const data = await window.api.get("/providers");
    const statusData = (await window.api.get("/providers/status")).providers || {};
    const grid = el("div", "card-grid");

    const PROVIDER_BRAND_ICONS = {
      "bpb-worker-panel": "bpb", "bpb-wizard": "bpb", zeus: "zeus",
      rvg: "rvg", aether: "aether", nova: "nova",
    };

    data.providers.forEach((p) => {
      const pc = el("div", "provider-card");
      const head = el("div", "head");
      const brandKey = PROVIDER_BRAND_ICONS[p.name];
      if (brandKey && window.JpnhIcons) {
        const logo = el("span", "brand-logo");
        logo.innerHTML = window.JpnhIcons.brandImg(brandKey, 32);
        head.appendChild(logo);
      }
      head.appendChild(el("h3", null, p.display_name || p.name));
      const st = statusData[p.name];
      head.appendChild(badge(st ? st.status : "unknown", st ? st.status : null));
      pc.appendChild(head);

      const meta = el("div", "meta");
      const bits = [];
      if (p.panel_url) bits.push(p.panel_url);
      if (p.repository_url) bits.push(p.repository_url);
      meta.textContent = bits.join(" · ") || (p.integration_type || "no metadata");
      pc.appendChild(meta);

      const actions = el("div", "actions");
      const addBtn = (label, fn) => {
        const b = el("button", "btn small", label);
        b.addEventListener("click", () => fn());
        actions.appendChild(b);
      };

      if (p.capabilities.includes("open")) {
        addBtn("Open", async () => {
          try {
            const r = await window.api.post(`/providers/${p.name}/open`);
            if (r.ok && r.url) window.ui.openPanel(r.url);
            else toast(r.error || "cannot open", "warn");
          } catch (err) { toast(err.message, "bad"); }
        });
      }
      if (p.capabilities.includes("configure")) {
        addBtn("Configure", () => configureModal(p));
      }
      if (p.capabilities.includes("import")) {
        addBtn("Import", () => importModal(p));
      }
      if (p.capabilities.includes("parse")) {
        addBtn("Parse", () => parseModal(p));
      }
      if (p.capabilities.includes("status")) {
        addBtn("Status", async () => {
          try {
            const r = await window.api.get(`/providers/${p.name}`);
            toast(`${p.name}: ${r.status || "ok"}`, "ok");
          } catch (err) { toast(err.message, "bad"); }
        });
      }

      pc.appendChild(actions);
      grid.appendChild(pc);
    });

    container.replaceChildren(
      card("Provider Hub", el("div", "muted mb",
        "Open, configure, import and parse configurations from each provider. The Hub never replaces the original panels.")),
      grid
    );
  },
};

function configureModal(p) {
  const { el, toast, openModal, closeModal, field } = window.ui;
  const input = el("input", "mono");
  input.type = "text";
  input.placeholder = "https://your-panel.example.com";
  const form = el("div");
  form.appendChild(field("Panel URL", input));
  openModal(`Configure ${p.display_name}`, form, [
    { label: "Cancel", kind: "ghost", onClick: (o) => closeModal(o) },
    {
      label: "Save",
      onClick: async (o) => {
        try {
          const r = await window.api.post(`/providers/${p.name}/configure`, { panel_url: input.value.trim() });
          if (r.ok) {
            toast(`Saved panel URL for ${p.name}`, "ok");
            closeModal(o);
            window.navigate("providers");
          } else toast(r.error || "failed", "bad");
        } catch (err) { toast(err.message, "bad"); }
      },
    },
  ]);
}

function importModal(p) {
  const { el, toast, openModal, closeModal, field } = window.ui;
  const ta = el("textarea");
  ta.placeholder = "Paste share links, subscription output, or generated configs…";
  const form = el("div");
  form.appendChild(field("Payload", ta));
  openModal(`Import into ${p.display_name}`, form, [
    { label: "Cancel", kind: "ghost", onClick: (o) => closeModal(o) },
    {
      label: "Parse",
      onClick: async (o) => {
        try {
          const r = await window.api.post(`/providers/${p.name}/parse`, { payload: ta.value });
          const count = (r.parsed || []).length;
          toast(`Parsed ${count} item(s)`, count ? "ok" : "warn");
          if (count) {
            closeModal(o);
            window.navigate("configs");
          }
        } catch (err) { toast(err.message, "bad"); }
      },
    },
  ]);
}

function parseModal(p) {
  const { el, toast, openModal, closeModal, field } = window.ui;
  const ta = el("textarea");
  ta.placeholder = "Paste a single share link to parse into normalized fields…";
  const form = el("div");
  form.appendChild(field("Payload", ta));
  openModal(`Parse from ${p.display_name}`, form, [
    { label: "Cancel", kind: "ghost", onClick: (o) => closeModal(o) },
    {
      label: "Parse",
      onClick: async (o) => {
        try {
          const r = await window.api.post(`/providers/${p.name}/parse`, { payload: ta.value });
          closeModal(o);
          showParseResult(r, p);
        } catch (err) { toast(err.message, "bad"); }
      },
    },
  ]);
}

function showParseResult(r, p) {
  const { el, openModal, closeModal, table } = window.ui;
  const items = r.results || r.parsed || [];
  const rows = items.map((item) => {
    const c = item.parsed || item.config || {};
    return [
      c.protocol || "-",
      c.address ? `${c.address}:${c.port}` : "-",
      c.security || "-",
      c.network || "-",
      item.error || (c.uuid || c.password || "-"),
    ];
  });
  const t = table(["Protocol", "Address", "Security", "Network", "Identity / Error"], rows);
  openModal(`Parsed result from ${p.display_name}`, t, [
    { label: "Close", kind: "ghost", onClick: (o) => closeModal(o) },
  ]);
}
