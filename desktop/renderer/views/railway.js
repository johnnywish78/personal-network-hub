"use strict";

window.Views = window.Views || {};

window.Views.railway = {
  async render(container) {
    const { el, card, badge, toast, statusDot, openPanel } = window.ui;
    const status = await window.api.get("/railway/status");

    const authCard = card("Authentication");
    const authBody = el("div");
    if (!status.configured) {
      authBody.appendChild(el("p", "muted mb", "No API token configured. Tokens are stored in the local secure vault."));
      const btn = el("button", "btn primary", "Set API Token");
      btn.addEventListener("click", () => window.tokenModal("railway", "/railway/auth"));
      authBody.appendChild(btn);
    } else {
      authBody.appendChild(el("div", "status-line", [
        statusDot(status.status === "ok" ? "ok" : "bad"),
        el("span", null, status.status === "ok" ? "Token valid" : "Token invalid"),
        el("span", "muted", status.error || ""),
      ]));
      const row = el("div", "row");
      const chg = el("button", "btn ghost small", "Change Token");
      chg.addEventListener("click", () => window.tokenModal("railway", "/railway/auth"));
      const rm = el("button", "btn danger small", "Remove");
      rm.addEventListener("click", async () => {
        await window.api.del("/railway/auth");
        toast("Token removed", "ok");
        window.refreshAll();
      });
      row.appendChild(chg);
      row.appendChild(rm);
      authBody.appendChild(row);
    }
    authCard._setBody(authBody);

    const dashBtn = el("button", "btn", "Open Railway Dashboard");
    dashBtn.addEventListener("click", async () => {
      const r = await window.api.get("/railway/dashboard-url");
      openPanel(r.url);
    });

    container.replaceChildren(authCard, card("Access", dashBtn));

    if (!status.configured) {
      container.appendChild(el("div", "card", el("div", "empty",
        "Configure a Railway token to browse projects, services and deployments.")));
      return;
    }

    try {
      const projects = await window.api.get("/railway/projects");
      const pc = card("Projects");
      const pbody = el("div");
      projects.projects.forEach((p) => {
        const line = el("div", "status-line");
        line.appendChild(statusDot("ok"));
        const label = el("span", null, p.name || "(untitled)");
        line.appendChild(label);
        const open = el("button", "btn small", "Open");
        open.addEventListener("click", () => openPanel(p.url));
        line.appendChild(open);
        pbody.appendChild(line);
      });
      if (!projects.projects.length) pbody.appendChild(el("div", "muted", "No projects accessible."));
      pc._setBody(pbody);
      container.appendChild(pc);
    } catch (err) {
      container.appendChild(el("div", "card", el("div", "empty", `Railway API error: ${err.message}`)));
    }
  },
};
