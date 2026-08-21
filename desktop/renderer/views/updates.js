"use strict";

// Updates Hub: Update Manager for JPNH core, vendored projects/components,
// and any registry-defined future projects. Backed by /updates + /projects.
//
// Design notes (requirements):
//   * Event-driven only — this view never installs an interval or a "seconds
//     counter"; it re-renders on user actions and when operations finish.
//   * Progress is textual + an indeterminate spinner. No fake percentages.
//   * Cached status renders immediately; a background check runs after first
//     paint and refreshes the cards when it returns.
//   * JPNH Core is staging-only: "Download & Stage" then "Restart & Update"
//     (source/dev mode). Packaged builds update JPNH Core with the JPNH release.

window.Views = window.Views || {};

const UPDATE_STATUS_LABEL = {
  "up-to-date": "✓ Up to date",
  "update-available": "Update available",
  installed: "Installed",
  missing: "Not installed",
  disabled: "Disabled",
  error: "⚠ Update failed",
  "no-stable-release": "No stable release",
  "newer-than-remote": "Local ahead of remote",
  staged: "Staged — restart to apply",
  unknown: "Unknown",
};

function statusBadge(status) {
  const cls = {
    "up-to-date": "ok",
    "update-available": "warn",
    installed: "ok",
    missing: "muted",
    disabled: "muted",
    error: "bad",
    "no-stable-release": "muted",
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

const viewState = {
  busyProject: null,
  operation: "",
  runtime: "source",
  pendingApply: null,
  appimageTarget: null,
  appimageSha256: null,
};

function setOperation(projectId, text) {
  viewState.busyProject = projectId || null;
  viewState.operation = text || "";
}

const cache = (function () {
  let value = null;
  return {
    get: () => value,
    set: (data) => { value = data; },
  };
})();

const PROJECT_BRAND_ICONS = {
  "jpnh-core": "jpnh",
  "network-checker": "network-checker",
};

function projectCard(project, onChanged) {
  const { el, toast } = window.ui;
  const card = el("div", "provider-card");
  const head = el("div", "head");
  const brandKey = PROJECT_BRAND_ICONS[project.id];
  if (brandKey && window.JpnhIcons) {
    const logo = el("span", "brand-logo");
    logo.innerHTML = window.JpnhIcons.brandImg(brandKey, 32);
    head.appendChild(logo);
  } else {
    head.appendChild(el("span", "service-icon", project.icon || "⇅"));
  }
  const titleWrap = el("div");
  titleWrap.appendChild(el("h3", null, project.name));
  const repo = project.repository
    ? `github.com/${project.repository}` : "no external source";
  titleWrap.appendChild(el("div", "meta mono", repo));
  head.appendChild(titleWrap);

  const managed = project.status === "unknown" && project.adopted &&
    project.current && project.current.installed;
  head.appendChild(managed ? window.ui.badge("Managed", "ok") : statusBadge(project.status));
  card.appendChild(head);

  const meta = el("div", "meta muted mono");
  const parts = [];
  if (project.install_path && project.install_path !== ".") {
    parts.push("path: " + project.install_path);
  }
  if (project.current && project.current.install_path) {
    const bundledNetworkChecker =
      project.id === "network-checker" &&
      project.health &&
      project.health.checks &&
      project.health.checks.some(
        (check) => check.name === "network-checker-bundle" && check.ok
      );

    if (bundledNetworkChecker) {
      parts.push("bundled: yes");
    } else {
      parts.push("installed: " + (project.current.installed ? "yes" : "no"));
    }
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

  if (project.health || project.build || project.backup_available !== undefined) {
    const summary = el("div", "meta mono mt");
    const bits = [];
    if (project.health) bits.push(project.health.ok ? "health: ✓" : "health: ✗");
    if (project.build && project.build.required) bits.push("build required");
    if (project.backup_available > 0) bits.push("backups: " + project.backup_available);
    if (bits.length) summary.textContent = bits.join("  ·  ");
    card.appendChild(summary);
  }

  if (project.adopted) {
    card.appendChild(el("div", "meta ok mt",
      "Adopted automatically from the existing installation — nothing was downloaded. Local changes are still detected."));
  }

  if (project.local_changes && project.local_changes.detected) {
    const warn = el("div", "meta warn mt");
    warn.textContent = "⚠ Local changes detected — updating may overwrite them" +
      (project.local_changes.files && project.local_changes.files.length
        ? " (e.g. " + project.local_changes.files.slice(0, 3).join(", ") + ")" : "");
    card.appendChild(warn);
  } else if (project.local_changes && project.local_changes.detected === null) {
    card.appendChild(el("div", "meta warn mt",
      "Installed, but not yet managed by the update manager. The first update backs it up and tracks it."));
  }

  if (project.status === "no-stable-release") {
    card.appendChild(el("div", "meta mt",
      project.note || "Repository reachable, but no stable release is published."));
  }

  if (project.error) {
    card.appendChild(el("div", "meta bad mt", "⚠ " + project.error));
  }

  card.appendChild(actionRow(project, onChanged));
  return card;
}

function actionRow(project, onChanged) {
  const actions = window.ui.el("div", "actions");
  if (project.id === "jpnh-core") return coreActions(project, onChanged, actions);

  const busy = viewState.busyProject === project.id;
  const canUpdate = project.enabled &&
    project.source_type !== "none" &&
    ["update-available", "installed", "unknown", "newer-than-remote", "error"].includes(project.status);

  if (canUpdate && !busy) {
    const btn = window.ui.el("button", "btn small primary", "Update");
    btn.addEventListener("click", () => updateProject(project, onChanged));
    actions.appendChild(btn);
  } else if (busy) {
    actions.appendChild(window.ui.el("span", "spinner", ""));
  }
  if (project.repository) {
    const link = window.ui.el("button", "btn small ghost", "Repo");
    link.addEventListener("click", () => window.ui.openExternal("https://github.com/" + project.repository));
    actions.appendChild(link);
  }
  return actions;
}

function coreActions(project, onChanged, actions) {
  const { el, toast, confirmDialog, openExternal } = window.ui;
  const busy = viewState.busyProject === project.id;
  const packaged = viewState.runtime !== "source";

  if (packaged && viewState.runtime === "appimage") {
    return appimageCoreActions(project, onChanged, actions);
  }

  if (packaged) {
    actions.appendChild(el("span", "meta muted mono",
      "JPNH Core ships inside this package. Install the new JPNH release to update it."));
    if (project.repository) {
      const rel = el("button", "btn small ghost", "Releases");
      rel.addEventListener("click", () => openExternal("https://github.com/" + project.repository + "/releases"));
      actions.appendChild(rel);
    }
    return actions;
  }

  const stagedReady = !!project.staged_ref && viewState.pendingApply === null;

  if (stagedReady) {
    const btn = el("button", "btn small primary", "Restart & Update");
    btn.addEventListener("click", () => restartAndUpdate(project, onChanged));
    actions.appendChild(btn);
    if (project.status === "update-available") {
      const restage = el("button", "btn small ghost", "Re-stage");
      restage.addEventListener("click", () => updateProject(project, onChanged, true));
      actions.appendChild(restage);
    }
    actions.appendChild(el("span", "meta muted mono", "staged: " + shortRef(project.staged_ref)));
  } else if (project.status === "update-available" && !busy) {
    const btn = el("button", "btn small primary", "Download & Stage");
    btn.addEventListener("click", () => updateProject(project, onChanged, true));
    actions.appendChild(btn);
  } else if (busy) {
    actions.appendChild(el("span", "spinner", ""));
  }
  if (project.repository) {
    const link = el("button", "btn small ghost", "Repo");
    link.addEventListener("click", () => openExternal("https://github.com/" + project.repository));
    actions.appendChild(link);
  }
  return actions;
}

// AppImage self-update flow: the user downloads the new AppImage release
// artifact, then restarts so the startup updater atomically replaces the
// INSTALLED AppImage (the file the desktop launcher runs) and relaunches into
// it. Nothing is ever truncated; the old binary is preserved as .old until the
// new build starts successfully.
function appimageCoreActions(project, onChanged, actions) {
  const { el, toast, confirmDialog, openExternal } = window.ui;
  const busy = viewState.busyProject === project.id;
  const pending = viewState.pendingApply;
  const stagedArtifact = project.staged_artifact || (pending && pending.appimage_artifact);

  actions.appendChild(el("span", "meta muted mono",
    "installed AppImage: " + (viewState.appimageTarget || "unknown")));

  if (pending && pending.appimage_artifact) {
    const btn = el("button", "btn small primary", "Restart & Apply");
    btn.addEventListener("click", () => restartAndUpdateAppImage(project, onChanged));
    actions.appendChild(btn);
    if (project.staged_artifact_sha256) {
      actions.appendChild(el("span", "meta mono",
        "staged sha256: " + String(project.staged_artifact_sha256).slice(0, 16) + "…"));
    }
    return actions;
  }

  if (stagedArtifact) {
    const btn = el("button", "btn small primary", "Restart & Apply");
    btn.addEventListener("click", () => restartAndUpdateAppImage(project, onChanged));
    actions.appendChild(btn);
    if (project.staged_artifact_sha256) {
      actions.appendChild(el("span", "meta mono",
        "staged sha256: " + String(project.staged_artifact_sha256).slice(0, 16) + "…"));
    }
    return actions;
  }

  if (project.status === "update-available" && !busy) {
    const btn = el("button", "btn small primary", "Download AppImage");
    btn.addEventListener("click", () => downloadAppImage(project, onChanged));
    actions.appendChild(btn);
  } else if (busy) {
    actions.appendChild(el("span", "spinner", ""));
  }
  if (project.repository) {
    const rel = el("button", "btn small ghost", "Releases");
    rel.addEventListener("click", () => openExternal("https://github.com/" + project.repository + "/releases"));
    actions.appendChild(rel);
  }
  return actions;
}

function downloadAppImage(project, onChanged) {
  const { toast, confirmDialog } = window.ui;
  confirmDialog(
    "Download AppImage",
    `Download the latest JPNH AppImage and apply it to the installed AppImage (` +
    (viewState.appimageTarget || "the desktop launcher target") + `)?\n\n` +
    `On restart, JPNH atomically replaces the installed AppImage (the old one is kept as .old until the new build starts) and relaunches.`,
    async () => {
      setOperation(project.id, "Downloading the JPNH AppImage…");
      onChanged();
      try {
        const r = await window.api.post(`/updates/${project.id}/stage-appimage`, {});
        if (r.ok && r.staged && r.staged.ok) {
          toast("AppImage downloaded and validated. Restart to apply.", "ok");
        } else {
          toast(r.error || (r.staged && r.staged.error) || "could not stage the AppImage", "bad");
        }
      } catch (err) {
        toast(err.message, "bad");
      }
      setOperation(null, "");
      onChanged();
    });
}

function restartAndUpdateAppImage(project, onChanged) {
  const { toast, confirmDialog } = window.ui;
  confirmDialog(
    "Restart & Apply AppImage",
    `JPNH will quit now. On the next launch the installed AppImage is replaced ` +
    `atomically (old binary kept as .old until the new build starts) and JPNH ` +
    `relaunches into the updated AppImage.\n\nContinue?`,
    async () => {
      try {
        const r = await window.api.post(`/updates/${project.id}/apply-appimage`);
        if (!r.ok) { toast(r.error || "could not schedule the AppImage apply", "bad"); return; }
        toast("Restarting to apply the AppImage update…", "info");
        setTimeout(() => { if (window.jpnh && window.jpnh.quit) window.jpnh.quit(); }, 400);
      } catch (err) {
        toast(err.message, "bad");
      }
    });
}

function restartAndUpdate(project, onChanged) {
  const { toast, confirmDialog } = window.ui;
  confirmDialog(
    "Restart & Update",
    `JPNH will quit now. On the next launch it applies the staged ${project.name} update (${project.staged_ref}) to the source tree, health-checks it, and rolls back automatically on any failure.\n\nContinue?`,
    async () => {
      try {
        const r = await window.api.post(`/updates/${project.id}/restart-apply`);
        if (!r.ok) { toast(r.error || "could not schedule restart", "bad"); return; }
        toast("Restarting to apply the staged update…", "info");
        setTimeout(() => { if (window.jpnh && window.jpnh.quit) window.jpnh.quit(); }, 400);
      } catch (err) {
        toast(err.message, "bad");
      }
    });
}

function updateProject(project, onChanged) {
  const { toast, confirmDialog } = window.ui;
  const localChanged = project.local_changes && project.local_changes.detected;
  const unmanaged = project.status === "installed" || project.status === "unknown";
  const needsConfirm = localChanged || (unmanaged && !project.adopted);
  const confirmMessage = needsConfirm
    ? `"${project.name}" is not yet managed by the update manager or has local changes. ` +
      "Updating backs it up first, then may overwrite existing files.\n\n" +
      "Do you want to continue?"
    : `Update "${project.name}" to the available version?`;

  const doUpdate = async (confirm) => {
    setOperation(project.id, `Updating ${project.name}… (backup → download → apply → build → health)`);
    onChanged();
    try {
      const r = await window.api.post(`/updates/${project.id}/update`, {
        project_id: project.id, confirm: !!confirm,
      });
      if (r.ok || r.result === "success" || r.result === "staged") {
        toast(`${project.name}: ${r.result === "staged" ? "staged — Restart & Update" : "updated"}`, "ok");
      } else {
        toast(`${project.name}: ${r.error || r.result}`, "bad");
      }
    } catch (err) {
      toast(err.message, "bad");
    }
    setOperation(null, "");
    onChanged();
  };

  if (needsConfirm) {
    confirmDialog(`Update ${project.name}`, confirmMessage, () => doUpdate(true));
  } else {
    doUpdate(false);
  }
}

function updateAll(onChanged) {
  const { toast } = window.ui;
  setOperation(null, "Updating all safe projects…");
  onChanged();
  window.api.post("/updates/all", { confirm: false }).then((data) => {
    const rows = (data.summary || []).map((s) => [s.name, s.status, s.old_version || "—", s.new_version || "—", s.error || ""]);
    showSummary(rows);
  }).catch((err) => toast(err.message, "bad"))
    .finally(() => {
      setOperation(null, "");
      onChanged();
    });
}

function showSummary(rows) {
  const { openModal, table } = window.ui;
  const modal = openModal("Update Summary", table(
    ["Project", "Result", "From", "To", "Detail"], rows));
  setTimeout(() => window.ui.closeModal(modal), 8000);
}

function showHistory() {
  const { openModal, table, toast } = window.ui;
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
  const { openModal, table, toast, confirmDialog } = window.ui;
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
    const { el, toast } = window.ui;

    const header = el("div", "row between");
    const heading = el("div");
    heading.appendChild(el("h2", null, "Updates"));
    heading.appendChild(el("p", "muted",
      "Check and apply updates for JPNH core and managed components. " +
      "Every update is backed up, built, and health-checked; failures roll back automatically."));
    header.appendChild(heading);

    const actions = el("div", "row");

    const btnCheck = el("button", "btn", "⟳ Check for Updates");
    btnCheck.addEventListener("click", async () => {
      btnCheck.disabled = true;
      setOperation(null, "Checking for updates…");
      refresh();
      try {
        await window.api.post("/updates/check", {});
        toast("Update check complete", "ok");
      } catch (err) {
        toast(err.message, "bad");
      }
      setOperation(null, "");
      btnCheck.disabled = false;
      await refresh();
    });
    actions.appendChild(btnCheck);

    const btnAll = el("button", "btn primary", "Update All");
    btnAll.addEventListener("click", () => {
      window.ui.confirmDialog(
        "Update All",
        "Update every managed project that is safe to update.\n\n" +
        "Projects with local changes, un-baselinable installs, development-only builds, " +
        "or no stable release are skipped and reported — never silently overwritten.",
        () => updateAll(refresh));
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

    const cards = el("div", "updates-cards");
    cards.id = "updates-cards";
    container.appendChild(cards);

    const drawCards = () => {
      cards.replaceChildren();
      if (viewState.operation) {
        const line = el("div", "card progress-card");
        line.appendChild(el("span", "spinner", ""));
        line.appendChild(el("span", "progress-text", viewState.operation));
        cards.appendChild(line);
        return;
      }
      const data = cache.get();
      const projects = (data && data.projects) || [];
      (data && data.errors || []).forEach((e) => cards.appendChild(el("div", "meta bad mt", "⚠ " + e)));
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
        list.forEach((p) => grid.appendChild(projectCard(p, refresh)));
        wrap.appendChild(grid);
        cards.appendChild(wrap);
      };
      section("JPNH Core", groups.core);
      section("Components", groups.component);
      section("Tools", groups.tools);
      section("Other Projects", groups.custom);
      if (!projects.length) {
        cards.appendChild(el("div", "card", el("div", "empty", "No managed projects.")));
      }
    };

    const refresh = async () => {
      try {
        const data = await window.api.get("/updates");
        cache.set(data);
        viewState.runtime = data.runtime || "source";
        viewState.pendingApply = data.pending_apply || null;
        viewState.appimageTarget = data.appimage_target || null;
        viewState.appimageSha256 = data.appimage_sha256 || null;
      } catch (err) {
        toast("Could not load update status: " + err.message, "bad");
      }
      drawCards();
    };

    // 1. cached status renders immediately (fast local overview)
    await refresh();

    // 2. background check after first paint; updates the cards when it returns
    window.api.post("/updates/check", {}).then(async () => {
      await refresh();
    }).catch(() => {
      // keep showing cached state; the user can retry with the Check button
      drawCards();
    });

    container.appendChild(el("p", "muted",
      "Tip: if GitHub is unreachable, activate your terminal proxy (HTTP_PROXY / HTTPS_PROXY / ALL_PROXY) and run the check again. JPNH never ships or requires a built-in VPN."));
  },
};