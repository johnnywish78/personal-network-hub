"use strict";

window.Views = window.Views || {};

window.Views.clients = {
  async render(container) {
    const { el, card, badge, statusDot, toast, field, openModal, closeModal } = window.ui;
    const data = await window.api.get("/clients");

    const CLIENT_BRAND_ICONS = { v2rayN: "v2rayn", hiddify: "hiddify", v2box: "v2box" };

    const c = card("Client Applications");
    const body = el("div");
    data.clients.forEach((cl) => {
      const line = el("div", "provider-card mb");
      const head = el("div", "head");
      const brandKey = CLIENT_BRAND_ICONS[cl.id];
      if (brandKey && window.JpnhIcons) {
        const logo = el("span", "brand-logo");
        logo.innerHTML = window.JpnhIcons.brandImg(brandKey, 32);
        head.appendChild(logo);
      }
      head.appendChild(el("h3", null, cl.name));
      head.appendChild(badge(cl.detected ? "Detected" : "Not found", cl.detected ? "ok" : "muted"));
      line.appendChild(head);
      line.appendChild(el("div", "meta", `${cl.hint}${cl.path ? ` · ${cl.path}` : ""}`));

      const actions = el("div", "actions");
      if (cl.detected && cl.path) {
        const launch = el("button", "btn small primary", "Launch");
        launch.addEventListener("click", () => toast(`Launching ${cl.name} is done by your OS; open it from its own icon.`, "info"));
        actions.appendChild(launch);
      }
      const setPath = el("button", "btn small", "Set Path");
      setPath.addEventListener("click", () => pathModal(cl));
      actions.appendChild(setPath);
      line.appendChild(actions);
      body.appendChild(line);
    });

    c._setBody(body);
    container.appendChild(c);

    const note = card("Hand-off");
    note._setBody(el("p", "muted",
      "The Hub is not a proxy client. Copy a config URI / JSON or open your client to import it there."));
    container.appendChild(note);
  },
};

function pathModal(cl) {
  const { el, toast, openModal, closeModal, field } = window.ui;
  const input = el("input", "mono");
  input.value = cl.path || "";
  input.placeholder = "Absolute path to the client executable";
  const form = el("div");
  form.appendChild(field("Executable path", input));
  openModal(`Set path for ${cl.name}`, form, [
    { label: "Cancel", kind: "ghost", onClick: (o) => closeModal(o) },
    {
      label: "Save",
      onClick: async (o) => {
        try {
          await window.api.post(`/clients/${cl.id}/path`, { path: input.value.trim() });
          toast(`Path saved for ${cl.name}`, "ok");
          closeModal(o);
          window.refreshAll();
        } catch (err) { toast(err.message, "bad"); }
      },
    },
  ]);
}
