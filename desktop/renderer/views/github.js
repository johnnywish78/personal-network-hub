"use strict";

window.Views = window.Views || {};

window.Views.github = {
  async render(container) {
    const { el, card, badge, toast, statusDot, openPanel, confirmDialog } = window.ui;
    const status = await window.api.get("/github/status");

    const authCard = card("Authentication");
    const authBody = el("div");
    const ghHead = el("div", "row mb");
    if (window.JpnhIcons) {
      const ghLogo = el("span", "brand-logo");
      ghLogo.innerHTML = window.JpnhIcons.brandImg("github", 32, 1.3);
      ghHead.appendChild(ghLogo);
    }
    if (!status.configured) {
      authBody.appendChild(ghHead);
      authBody.appendChild(el("p", "muted mb", "No token configured. Optional, but recommended for higher rate limits."));
      const btn = el("button", "btn primary", "Set Token");
      btn.addEventListener("click", () => window.tokenModal("github", "/github/auth"));
      authBody.appendChild(btn);
    } else {
      authBody.appendChild(el("div", "status-line", [
        statusDot(status.status === "ok" ? "ok" : "bad"),
        el("span", null, status.authenticated ? `Authenticated as ${status.user}` : "Token present"),
        el("span", "muted", status.error || ""),
      ]));
      const row = el("div", "row");
      const chg = el("button", "btn ghost small", "Change Token");
      chg.addEventListener("click", () => window.tokenModal("github", "/github/auth"));
      const rm = el("button", "btn danger small", "Remove");
      rm.addEventListener("click", async () => {
        await window.api.del("/github/auth");
        toast("Token removed", "ok");
        window.refreshAll();
      });
      row.appendChild(chg);
      row.appendChild(rm);
      authBody.appendChild(row);
    }
    authCard._setBody(authBody);

    container.replaceChildren(authCard);

    // Known repositories
    let repos;
    try {
      repos = await window.api.get("/github/repos");
    } catch (err) {
      container.appendChild(el("div", "card", el("div", "empty", `GitHub API error: ${err.message}`)));
      return;
    }

    const knownCard = card("Known Repositories");
    const grid = el("div", "card-grid");
    (repos.known || []).forEach((k) => {
      const pc = el("div", "provider-card");
      const head = el("div", "head");
      head.appendChild(el("h3", null, k.name));
      pc.appendChild(head);
      pc.appendChild(el("div", "meta mono", k.repo));
      const actions = el("div", "actions");
      const openBtn = el("button", "btn small", "Open");
      openBtn.addEventListener("click", () => openPanel(`https://github.com/${k.repo}`));
      actions.appendChild(openBtn);
      const issuesBtn = el("button", "btn small ghost", "Issues");
      issuesBtn.addEventListener("click", () => openPanel(`https://github.com/${k.repo}/issues`));
      actions.appendChild(issuesBtn);
      const readmeBtn = el("button", "btn small ghost", "README");
      readmeBtn.addEventListener("click", () => openPanel(`https://github.com/${k.repo}#readme`));
      actions.appendChild(readmeBtn);
      const relBtn = el("button", "btn small ghost", "Release");
      relBtn.addEventListener("click", () => openPanel(`https://github.com/${k.repo}/releases/latest`));
      actions.appendChild(relBtn);
      pc.appendChild(actions);
      grid.appendChild(pc);
    });
    knownCard._setBody(grid);
    container.appendChild(knownCard);

    // Repository metadata with details
    const found = repos.repos.filter((r) => !r.error);
    if (found.length) {
      const detailCard = card("Repository Details");
      const rows = found.map((r) => [
        el("span", "mono", r.name),
        r.stargazers ?? "-",
        r.forks ?? "-",
        r.language || "-",
        r.license || "-",
        el("span", "muted", (r.updated_at || "-").slice(0, 10)),
        (() => {
          const wrap = el("div", "actions");
          const b = el("button", "btn small", "Open");
          b.addEventListener("click", () => openPanel(r.url));
          wrap.appendChild(b);
          return wrap;
        })(),
      ]);
      detailCard._setBody(window.ui.table(
        ["Repo", "Stars", "Forks", "Lang", "License", "Updated", ""],
        rows
      ));
      container.appendChild(detailCard);
    }
  },
};
