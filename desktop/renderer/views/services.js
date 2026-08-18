"use strict";

// Services Hub: cards for every integrated service with live status,
// open-in-browser, favorites, add/remove, and per-provider management.

window.Views = window.Views || {};

const SERVICE_CATEGORY_LABELS = {
  provider: "Providers",
  cloud: "Cloud Services",
  source: "Source Control",
  runtime: "Runtime",
  tools: "Tools",
  custom: "Custom",
};

const SERVICE_MANAGE_VIEW = {
  github: "github",
  cloudflare: "cloudflare",
  railway: "railway",
  "bpb-worker-panel": "providers",
  "bpb-wizard": "providers",
  zeus: "providers",
  rvg: "providers",
  aether: "providers",
  nova: "providers",
  "network-checker": "checker",
  xray: "xray",
};

function statusLabel(status) {
  return {
    ok: "ok",
    error: "error",
    "not-configured": "needs setup",
    "not-installed": "not installed",
    configured: "configured",
    unknown: "unknown",
  }[status] || status;
}

function openService(service) {
  const { toast, openExternal } = window.ui;
  window.api.post(`/services/${service.id}/open`).then((r) => {
    if (!r.ok) { toast(r.error || "cannot open", "bad"); return; }
    if (r.mode === "xray") { window.navigate("xray"); return; }
    if (r.mode === "launcher" && r.app === "network-checker") {
      launchNetworkCheckerApp();
      return;
    }
    if (r.mode === "launcher") { toast("Launching " + (service.name || ""), "ok"); return; }
    if (r.url) openBrowserFor(service, r.url);
  }).catch((err) => toast(err.message, "bad"));
}

function launchNetworkCheckerApp() {
  const { toast } = window.ui;
  window.jpnh.networkChecker.launch().then((r) => {
    if (r && r.ok) toast("Network Checker launched", "ok");
    else toast((r && r.error) || "Network Checker could not be launched", "bad");
  }).catch((err) => toast(err.message, "bad"));
}

function openBrowserFor(service, url) {
  const { openBrowser } = window.ui;
  if (service.open_mode === "external") window.ui.openExternal(url);
  else openBrowser(url, service.name);
}

function addToFavorites(service) {
  const { toast } = window.ui;
  window.api.post("/services/favorites", {
    id: service.id, name: service.name, url: service.url || "https://github.com/" + (service.repo || service.name),
    pinned: true,
  }).then(() => toast("Added to favorites", "ok")).catch((e) => toast(e.message, "bad"));
}

function serviceCard(service, { onChanged }) {
  const { el, badge, toast, confirmDialog, openModal, closeModal, field } = window.ui;
  const card = el("div", "service-card");
  const head = el("div", "service-head");
  head.appendChild(el("span", "service-icon", service.icon || "▧"));
  const titleWrap = el("div", "service-title");
  titleWrap.appendChild(el("h3", null, service.name));
  titleWrap.appendChild(el("div", "meta mono", service.type || service.id));
  head.appendChild(titleWrap);
  head.appendChild(badge(statusLabel(service.status && service.status.status), service.status && service.status.status));
  card.appendChild(head);

  if (service.status && service.status.detail) {
    card.appendChild(el("div", "meta muted mono", service.status.detail));
  }

  const actions = el("div", "actions");
  if (service.url || service.open_mode !== "api") {
    const openBtn = el("button", "btn small", "Open");
    openBtn.addEventListener("click", () => openService(service));
    actions.appendChild(openBtn);
  }
  const favBtn = el("button", "btn small ghost", "★");
  favBtn.title = "Add to favorites";
  favBtn.addEventListener("click", () => addToFavorites(service));
  actions.appendChild(favBtn);

  if (SERVICE_MANAGE_VIEW[service.id]) {
    const mgrBtn = el("button", "btn small ghost", "Manage");
    mgrBtn.addEventListener("click", () => window.navigate(SERVICE_MANAGE_VIEW[service.id]));
    actions.appendChild(mgrBtn);
  }

  // presets with no URL yet (panels) can be configured inline
  if (!service.url && service.integration_type === "provider_adapter") {
    const cfgBtn = el("button", "btn small ghost", "Set URL");
    cfgBtn.addEventListener("click", () => configureUrl(service, onChanged));
    actions.appendChild(cfgBtn);
  }

  if (service.user) {
    const rmBtn = el("button", "btn small danger", "✕");
    rmBtn.title = "Remove service";
    rmBtn.addEventListener("click", () => confirmDialog("Remove service", `Remove "${service.name}"?`, async () => {
      await window.api.del(`/services/${service.id}`);
      toast("Removed", "ok");
      onChanged();
    }));
    actions.appendChild(rmBtn);
  }
  card.appendChild(actions);
  return card;
}

function configureUrl(service, onChanged) {
  const { el, toast, openModal, closeModal, field } = window.ui;
  const input = el("input", "mono");
  input.placeholder = "https://panel.example.com/uuid";
  const form = el("div");
  form.appendChild(field("Panel / service URL", input));
  form.appendChild(el("p", "muted", "Stored in local settings only."));
  openModal(`Configure ${service.name}`, form, [
    { label: "Cancel", kind: "ghost", onClick: (o) => closeModal(o) },
    {
      label: "Save",
      onClick: async (o) => {
        try {
          const url = input.value.trim();
          if (!/^https?:\/\//i.test(url)) { toast("Enter a valid http(s) URL", "bad"); return; }
          const r = await window.api.patch(`/services/${service.id}`, { url });
          if (r.ok) {
            toast("Saved", "ok");
            closeModal(o);
            onChanged();
          } else toast(r.error || "failed", "bad");
        } catch (err) { toast(err.message, "bad"); }
      },
    },
  ]);
}

function addServiceForm(onChanged) {
  const { el, toast, openModal, closeModal, field } = window.ui;
  const name = el("input");
  name.placeholder = "My Service";
  const url = el("input", "mono");
  url.placeholder = "https://example.com";
  const type = el("select");
  ["tool", "panel", "dashboard", "checker", "runtime"].forEach((t) => {
    const o = el("option");
    o.value = t; o.textContent = t;
    type.appendChild(o);
  });
  const category = el("select");
  ["custom", "cloud", "source", "runtime", "tools"].forEach((t) => {
    const o = el("option");
    o.value = t; o.textContent = t;
    category.appendChild(o);
  });
  const mode = el("select");
  [["embedded", "Browser Hub (embedded)"], ["external", "System browser"]].forEach(([v, l]) => {
    const o = el("option");
    o.value = v; o.textContent = l;
    mode.appendChild(o);
  });
  const form = el("div");
  form.appendChild(field("Name *", name));
  form.appendChild(field("URL", url));
  form.appendChild(field("Type", type));
  form.appendChild(field("Category", category));
  form.appendChild(field("Open mode", mode));
  openModal("Add service", form, [
    { label: "Cancel", kind: "ghost", onClick: (o) => closeModal(o) },
    {
      label: "Add",
      onClick: async (o) => {
        try {
          if (!name.value.trim()) { toast("Name is required", "bad"); return; }
          const r = await window.api.post("/services", {
            name: name.value.trim(),
            url: url.value.trim(),
            type: type.value,
            category: category.value,
            open_mode: mode.value,
          });
          if (r.ok) {
            toast("Service added", "ok");
            closeModal(o);
            onChanged();
          } else toast(r.error || "failed", "bad");
        } catch (err) { toast(err.message, "bad"); }
      },
    },
  ]);
}

window.Views.services = {
  async render(container, params) {
    const { el, card } = window.ui;
    const data = await window.api.get("/services");
    const services = data.services || [];

    const renderAll = async () => {
      container.replaceChildren();

      const header = el("div", "row between");
      const heading = el("div");
      heading.appendChild(el("h2", null, "Service Registry"));
      heading.appendChild(el("p", "muted", "All integrated services with live status. Open any service in the Browser Hub."));
      header.appendChild(heading);
      const addBtn = el("button", "btn primary", "＋ Add Service");
      addBtn.addEventListener("click", () => addServiceForm(renderAll));
      header.appendChild(addBtn);
      container.appendChild(header);

      const refresh = await window.api.get("/services");
      const groups = {};
      (refresh.services || []).forEach((s) => {
        const key = s.category || "custom";
        if (!groups[key]) groups[key] = [];
        groups[key].push(s);
      });

      Object.entries(groups).forEach(([cat, list]) => {
        const grid = el("div", "service-grid");
        list.forEach((s) => grid.appendChild(serviceCard(s, { onChanged: renderAll })));
        const wrap = el("div");
        wrap.appendChild(el("h3", "section-title", SERVICE_CATEGORY_LABELS[cat] || cat));
        wrap.appendChild(grid);
        container.appendChild(wrap);
      });

      if (!refresh.services.length) {
        container.appendChild(el("div", "card", el("div", "empty", "No services registered.")));
      }
    };

    await renderAll();
  },
};