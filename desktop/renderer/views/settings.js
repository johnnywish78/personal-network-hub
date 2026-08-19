"use strict";

window.Views = window.Views || {};

window.Views.settings = {
  async render(container) {
    const { el, card, badge, toast } = window.ui;
    const version = await window.api.get("/version");
    const authStatus = await window.api.get("/auth/status");

    const about = card("About");
    const aboutBody = el("div");
    const rows = [
      ["Name", version.name],
      ["Codename", version.codename],
      ["Version", version.version],
      ["Data directory", window.api.getBaseUrl()],
    ];
    rows.forEach(([k, v]) => {
      const line = el("div", "status-line");
      line.appendChild(el("span", "status-label", k));
      line.appendChild(el("span", "mono", v));
      aboutBody.appendChild(line);
    });
    about._setBody(aboutBody);

    const theme = card("Interface");
    const themeRow = el("div", "row");
    const themeLabel = el("span", "field-label", "Theme");
    const themeSelect = el("select");
    ["system", "dark", "light"].forEach((t) => {
      const opt = el("option", null, t[0].toUpperCase() + t.slice(1));
      opt.value = t;
      if (window.Theme && window.Theme.getMode() === t) opt.selected = true;
      themeSelect.appendChild(opt);
    });
    themeSelect.addEventListener("change", () => {
      if (window.Theme) window.Theme.setMode(themeSelect.value);
      toast("Theme saved", "ok");
    });
    themeRow.appendChild(themeLabel);
    themeRow.appendChild(themeSelect);
    theme._setBody(themeRow);

    const secrets = card("Stored Credentials (masked)");
    const secretsBody = el("div");
    const list = el("div", "pill-list");
    (authStatus.configured.cloudflare ? ["cloudflare"] : [])
      .concat(authStatus.configured.railway ? ["railway"] : [])
      .concat(authStatus.configured.github ? ["github"] : [])
      .forEach((k) => list.appendChild(badge(`${k} token`, "ok")));
    (authStatus.other_keys || []).forEach((k) => list.appendChild(badge(k, "muted")));
    if (!list.children.length) list.appendChild(el("span", "muted", "No credentials stored."));
    secretsBody.appendChild(list);
    secretsBody.appendChild(el("p", "muted mt",
      "Secret values are stored in the local vault (~/.jpnh/secrets.json, permissions 0600). They are never logged or exposed via the API."));
    secrets._setBody(secretsBody);

    container.replaceChildren(about, theme, secrets);
  },
};
