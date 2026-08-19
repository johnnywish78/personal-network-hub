"use strict";

window.Views = window.Views || {};

window.Views.cloudflare = {
  async render(container) {
    const { el, card, badge, toast, openModal, closeModal, field, statusDot, openPanel } = window.ui;
    const status = await window.api.get("/cloudflare/status");

    // Auth card
    const authCard = card("Authentication");
    const authBody = el("div");
    if (!status.configured) {
      authBody.appendChild(el("p", "muted mb", "No API token configured. Tokens are stored in the local secure vault."));
      const btn = el("button", "btn primary", "Set API Token");
      btn.addEventListener("click", () => tokenModal("cloudflare", "/cloudflare/auth"));
      authBody.appendChild(btn);
    } else {
      authBody.appendChild(el("div", "status-line", [
        statusDot(status.status === "ok" ? "ok" : "bad"),
        el("span", null, status.status === "ok" ? "Token valid" : "Token invalid"),
        el("span", "muted", status.error || ""),
      ]));
      const row = el("div", "row");
      const chg = el("button", "btn ghost small", "Change Token");
      chg.addEventListener("click", () => tokenModal("cloudflare", "/cloudflare/auth"));
      const rm = el("button", "btn danger small", "Remove");
      rm.addEventListener("click", async () => {
        await window.api.del("/cloudflare/auth");
        toast("Token removed", "ok");
        window.refreshAll();
      });
      row.appendChild(chg);
      row.appendChild(rm);
      authBody.appendChild(row);
    }
    authCard._setBody(authBody);

    const dashBtn = el("button", "btn", "Open Cloudflare Dashboard");
    dashBtn.addEventListener("click", async () => {
      const r = await window.api.get("/cloudflare/dashboard-url");
      openPanel(r.url);
    });
    const dashCard = card("Access", dashBtn);
    dashCard._setBody(dashBtn);

    container.replaceChildren(authCard, dashCard);

    if (!status.configured) {
      container.appendChild(el("div", "card", el("div", "empty",
        "Configure an API token to browse accounts, zones, workers and pages.")));
      return;
    }

    // Accounts
    try {
      const acc = await window.api.get("/cloudflare/accounts");
      const ac = card("Accounts");
      const body = el("div");
      acc.accounts.forEach((a) => {
        const line = el("div", "status-line");
        line.appendChild(statusDot("ok"));
        line.appendChild(el("span", "mono", a.name));
        body.appendChild(line);
      });
      if (!acc.accounts.length) body.appendChild(el("div", "muted", "No accounts accessible."));
      ac._setBody(body);
      container.appendChild(ac);

      // Workers list (first account)
      const firstId = acc.accounts[0] && acc.accounts[0].id;
      if (firstId) {
        const w = await window.api.get(`/cloudflare/workers/${firstId}`);
        const wc = card("Workers");
        const wbody = el("div");
        w.workers.forEach((wk) => {
          const line = el("div", "status-line");
          line.appendChild(statusDot("ok"));
          line.appendChild(el("span", "mono", wk.id));
          wbody.appendChild(line);
        });
        if (!w.workers.length) wbody.appendChild(el("div", "muted", "No workers found."));
        wc._setBody(wbody);
        container.appendChild(wc);
      }
    } catch (err) {
      container.appendChild(el("div", "card", el("div", "empty", `Cloudflare API error: ${err.message}`)));
    }
  },
};

function tokenModal(svcName, path) {
  const { el, toast, openModal, closeModal, field } = window.ui;
  const input = el("input", "mono");
  input.type = "password";
  input.placeholder = "Paste API token…";
  const form = el("div");
  form.appendChild(field("Token", input));
  form.appendChild(el("p", "muted", "Stored only in the local secure vault. Never committed or logged."));
  openModal(`Set ${svcName} token`, form, [
    { label: "Cancel", kind: "ghost", onClick: (o) => closeModal(o) },
    {
      label: "Save",
      onClick: async (o) => {
        try {
          const r = await window.api.post(path, { token: input.value.trim() });
          if (r.ok) {
            toast(`${svcName} token saved`, "ok");
            closeModal(o);
            window.refreshAll();
          } else toast(r.error || "failed", "bad");
        } catch (err) { toast(err.message, "bad"); }
      },
    },
  ]);
}

window.tokenModal = tokenModal;
