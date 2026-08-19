"use strict";

// Updates Hub: Update Manager for JPNH core, vendored projects/components,
// and any registry-defined future projects. Backed by /updates + /projects.

window.Views = window.Views || {};

const UPDATE_STATUS_LABEL = {
  "up-to-date": "✓ Up to date",
  "update-available": "Update available",
  untracked: "Untracked install",
  disabled: "Disabled",
  error: "⚠ Update failed",
  "newer-than-remote": "Local ahead of remote",
  staged: "Staged — restart to apply",
  unknown: "Unknown",
};

function statusBadge(status) {
  const cls = {
    "up-to-date": "ok",
    "update-available": "warn",
    untracked: "warn",
    disabled: "muted",
    error: "bad",
    "newer-than-remote": "ok",
    staged: "ok",
    unknown: "muted",
  }[status] || "muted";
  return window.ui.badge(UPDATE_STATUS_LABEL[status] || status, cls);
}

function versionText(entry, key) {
  const v = entry && entry[key];
  if (!v) return "—";
  return String(v);
}

function shortRef(ref) {
  if (!ref) return "";
  return String(ref).length > 12 ? String(ref).slice(0, 12) + "…" : String(ref);
}

function projectCard(project, { onChanged, busy }) {
  const { el, badge, toast, confirmDialog, openExternal } = window.ui;
  const card = el("div", "provider-card");
  const head = el("div", "head");
  head.appendChild(el("span", "service-icon", project.icon || "⇅"));
  const titleWrap = el("div");
  titleWrap.appendChild(el("h3", null, project.name));
  const repo = project.repository
    ? `github.com/${project.repository}` : "no external source";
  titleWrap.appendChild(el("div", "meta mono", repo));
  head.appendChild(titleWrap);
  head.appendChild(statusBadge(project.status));
  card.appendChild(head);

  const meta = el("div", "meta muted mono");
  const parts = [];
  if (project.install_path && project.install_path !== ".") {
    parts.push("path: " + project.install_path);
  }
  if (project.current && project.current.install_path) {
    parts.push("installed: " + (project.current.installed ? "yes" : "no"));
  }
  if (project.last_update) parts.push("updated: " + String(project.last_update).slice(0, 16).replace("T", " "));
  meta.textContent = parts.join("  ·  ");
  card.appendChild(meta);

  const versions = el("div", "status-line");
  versions.appendChild(el("span", "status-label", "Current"));
  versions.appendChild(el("span", "mono",
    `${versionText(project.current, "version")}${shortRef(project.current && project.current.ref) ? "  (" + shortRef(project.current.ref) + ")" : ""}`));
  card.appendChild(versions);

  if (project.available && project.available.version !== undefined) {
    const avail = el("div", "status-line");
    avail.appendChild(el("span", "status-label", "Available"));
    avail.appendChild(el("span", "mono",
      `${versionText(project.available, "version")}${shortRef(project.available.ref) ? "  (" + shortRef(project.available.ref) + ")" : ""}${project.available.development ? "  (development)" : ""}`));
    card.appendChild(avail);
  }

  if (project.local_changes && project.local_changes.detected) {
    const warn = el("div", "meta warn mt");
    warn.textContent = "⚠ Local changes detected — updating may overwrite them" +
      (project.local_changes.files && project.local_changes.files.length
        ? " (e.g. " + project.local_changes.files.slice(0, 3).join(", ") + ")" : "");
    card.appendChild(warn);
  } else if (project.local_changes && project.local_changes.detected === null) {
    card.appendChild(el("div", "meta warn mt",
      "Installation is not tracked by the update manager. An update will record and sync it."));
  }

  if (project.error) {
    card.appendChild(el("div", "meta bad mt", "⚠ " + project.error));
  }

  const actions = el("div", "actions");
  const canUpdate = project.enabled &&
    project.source_type !== "none" &&
    ["update-available", "untracked", "unknown", "newer-than-remote", "error"].includes(project.status);

  if (canUpdate && !busy) {
    const btn = el("button", "btn small primary", "Update");
    btn.addEventListener("click", () => updateProject(project, onChanged));
    actions.appendChild(btn);
  }
  if (project.status === "staged" && project.staged_ref) {
    actions.appendChild(el("span", "meta muted mono", "staged: " + shortRef(project.staged_ref)));
  }
  if (project.repository) {
    const link = el("button", "btn small ghost", "Repo");
    link.addEventListener("click", () => openExternal("https://github.com/" + project.repository));
    actions.appendChild(link);
  }
  card.appendChild(actions);
  return card;
}

function updateProject(project, onChanged) {
  const { toast, confirmDialog } = window.ui;
  const localChanged = project.local_changes && project.local_changes.detected;
  const confirmMessage = localChanged
    ? `Local changes were detected in "${project.name}". Updating may overwrite them.\n\nDo you want to continue?`
    : `Update "${project.name}" to the available version?`;

  const doUpdate = async (confirm) => {
    try {
      const r = await window.api.post(`/updates/${project.id}/update`, {
        project_id: project.id, confirm: !!confirm,
      });
      if (r.ok || r.result === "success" || r.result === "staged") {
        toast(`${project.name}: ${r.result === "staged" ? "staged for next launch" : "updated"}`, "ok");
      } else {
        toast(`${project.name}: ${r.error || r.result}`, "bad");
      }
      onChanged();
    } catch (err) {
      toast(err.message, "bad");
    }
  };

  if (localChanged) {
    confirmDialog(`Update ${project.name}`, confirmMessage, () => doUpdate(true));
  } else {
    doUpdate(false);
  }
}

function updateAll(onChanged) {
  const { toast } = window.ui;
  toast("Updating all projects…", "info");
  window.api.post("/updates/all", { confirm: false }).then((data) => {
    const rows = (data.summary || []).map((s) => [s.name, s.status, s.old_version || "—", s.new_version || "—", s.error || ""]);
    showSummary(rows);
    onChanged();
  }).catch((err) => toast(err.message, "bad"));
}

function showSummary(rows) {
  const { el, openModal, table } = window.ui;
  const modal = openModal("Update Summary", table(
    ["Project", "Result", "From", "To", "Detail"], rows));
  setTimeout(() => window.ui.closeModal(modal), 6000);
}

function showHistory() {
  const { el, openModal, table, toast } = window.ui;
  window.api.get("/updates/history").then((data) => {
    const rows = (data.history || []).map((h) => [
      String(h.timestamp).slice(0, 16).replace("T", " "),
      h.project,
      h.result,
      h.old_version || "—",
      h.new_version || "—",
      h.error || "",
    ]);
    openModal("Update History",
      table(["Time", "Project", "Result", "From", "To", "Detail"], rows));
  }).catch((err) => toast(err.message, "bad"));
}

function showBackups() {
  const { el, openModal, table, toast, confirmDialog } = window.ui;
  window.api.get("/updates/backups").then((data) => {
    const backups = data.backups || [];
    const rows = backups.map((b) => [
      String(b.created_at).slice(0, 16).replace("T", " "),
      b.project,
      b.backup_id,
    ]);
    const body = table(["Created", "Project", "Backup id"], rows);
    openModal("Backups", body, backups.length ? [{
      label: "Roll back latest", kind: "danger",
      onClick: (o) => {
        window.ui.closeModal(o);
        confirmDialog("Roll back", `Restore the latest backup (${backups[0].backup_id})?`, async () => {
          try {
            const r = await window.api.post(`/updates/rollback/${backups[0].backup_id}`);
            toast(r.ok ? "Rolled back" : (r.error || "rollback failed"), r.ok ? "ok" : "bad");
          } catch (err) { toast(err.message, "bad"); }
        });
      },
    }] : []);
  }).catch((err) => toast(err.message, "bad"));
}

window.Views.updates = {
  async render(container, params) {
    const { el, card, toast } = window.ui;
    let busy = false;

    const renderAll = async () => {
      container.replaceChildren();
      if (busy) { container.appendChild(el("div", "empty", el("span", "spinner", ""))); return; }

      const header = el("div", "row between");
      const heading = el("div");
      heading.appendChild(el("h2", null, "Updates"));
      heading.appendChild(el("p", "muted",
        "Check and apply updates for JPNH core and managed components. " +
        "Every update is backed up and health-checked; failures roll back automatically."));
      header.appendChild(heading);

      const actions = el("div", "row");
      const btnCheck = el("button", "btn", "⟳ Check for Updates");
      btnCheck.addEventListener("click", async () => {
        busy = true; renderAll();
        try { await window.api.post("/updates/check", {}); }
        catch (err) { toast(err.message, "bad"); }
        busy = false; renderAll();
      });
      actions.appendChild(btnCheck);

      const btnAll = el("button", "btn primary", "Update All");
      btnAll.addEventListener("click", async () => {
        busy = true; renderAll();
        try { await updateAll(renderAll); }
        catch (err) { toast(err.message, "bad"); }
        busy = false; renderAll();
      });
      actions.appendChild(btnAll);

      const btnHist = el("button", "btn ghost", "History");
      btnHist.addEventListener("click", showHistory);
      actions.appendChild(btnHist);

      const btnBak = el("button", "btn ghost", "Backups");
      btnBak.addEventListener("click", showBackups);
      actions.appendChild(btnBak);

      header.appendChild(actions);
      container.appendChild(header);

      let data;
      let projects;
      try {
        data = await window.api.get("/updates");
        projects = data.projects || [];
      } catch (err) {
        container.appendChild(el("div", "card", el("div", "empty", `Failed to load update status: ${err.message}`)));
        return;
      }

      (data.errors || []).forEach((e) => container.appendChild(el("div", "meta bad mt", "⚠ " + e)));

      const groups = { core: [], component: [], tools: [], custom: [] };
      projects.forEach((p) => {
        const key = ["core", "component", "tools"].includes(p.category) ? p.category : "custom";
        groups[key].push(p);
      });

      const section = (title, list) => {
        if (!list.length) return;
        const wrap = el("div");
        wrap.appendChild(el("h3", "section-title", title));
        const grid = el("div", "service-grid");
        list.forEach((p) => grid.appendChild(projectCard(p, { onChanged: renderAll, busy })));
        wrap.appendChild(grid);
        container.appendChild(wrap);
      };

      section("JPNH Core", groups.core);
      section("Components", groups.component);
      section("Tools", groups.tools);
      section("Other Projects", groups.custom);
      if (!projects.length) {
        container.appendChild(el("div", "card", el("div", "empty", "No managed projects.")));
      }
      container.appendChild(el("p", "muted",
        "Tip: if GitHub is unreachable, activate your terminal proxy (HTTP_PROXY / HTTPS_PROXY / ALL_PROXY) and run the check again. JPNH never ships or requires a built-in VPN."));
    };

    await renderAll();
  },
};