"use strict";

window.DownloadBar = (function () {
  let barEl = null;
  let listEl = null;
  let downloads = [];

  function create() {
    if (barEl) return;
    const { el } = window.ui;
    barEl = el("div", "download-bar hidden");

    const header = el("div", "download-header");
    const title = el("span", "download-title", "Downloads");
    const closeBtn = el("button", "btn small ghost", "\u2715");
    closeBtn.addEventListener("click", hide);
    header.appendChild(title);
    header.appendChild(closeBtn);

    listEl = el("div", "download-list");

    barEl.appendChild(header);
    barEl.appendChild(listEl);
  }

  function show() {
    create();
    barEl.classList.remove("hidden");
    renderList();
  }

  function hide() {
    if (barEl) barEl.classList.add("hidden");
  }

  function addDownload(info) {
    create();
    downloads.unshift({
      id: info.id,
      filename: info.filename,
      url: info.url,
      totalBytes: info.totalBytes,
      receivedBytes: 0,
      state: "progressing",
      savePath: info.savePath,
      progress: 0,
    });
    show();
    renderList();
  }

  function updateProgress(id, progress, receivedBytes, totalBytes) {
    const d = downloads.find((d) => d.id === id);
    if (d) {
      d.progress = progress;
      d.receivedBytes = receivedBytes || d.receivedBytes;
      d.totalBytes = totalBytes || d.totalBytes;
      renderList();
    }
  }

  function complete(id, state, savePath) {
    const d = downloads.find((d) => d.id === id);
    if (d) {
      d.state = state;
      d.progress = 1;
      if (savePath) d.savePath = savePath;
      renderList();
    }
  }

  function cancelDownload(id) {
    const d = downloads.find((d) => d.id === id);
    if (d) {
      d.state = "cancelled";
      renderList();
    }
  }

  function removeDownload(id) {
    downloads = downloads.filter((d) => d.id !== id);
    renderList();
  }

  function clearAll() {
    downloads = [];
    renderList();
  }

  function formatBytes(bytes) {
    if (bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(1) + " " + units[i];
  }

  function renderList() {
    if (!listEl) return;
    const { el } = window.ui;
    listEl.replaceChildren();

    if (downloads.length === 0) {
      listEl.appendChild(el("div", "empty", "No downloads"));
      return;
    }

    downloads.slice(0, 10).forEach((d) => {
      const item = el("div", "download-item");

      const name = el("span", "download-name", d.filename);
      name.title = d.url;
      item.appendChild(name);

      if (d.state === "progressing") {
        const progressWrap = el("div", "download-progress");
        const fill = el("div", "download-progress-fill");
        fill.style.width = (d.progress * 100) + "%";
        progressWrap.appendChild(fill);
        item.appendChild(progressWrap);

        const size = el("span", "download-size", formatBytes(d.receivedBytes) + " / " + formatBytes(d.totalBytes));
        item.appendChild(size);

        const cancelBtn = el("button", "btn small ghost", "\u2715");
        cancelBtn.addEventListener("click", () => cancelDownload(d.id));
        item.appendChild(cancelBtn);
      } else {
        const statusEl = el("span", "download-status " + d.state, d.state);
        item.appendChild(statusEl);

        if (d.state === "completed" && d.savePath) {
          const openBtn = el("button", "btn small ghost", "Open");
          openBtn.addEventListener("click", () => {
            if (window.jpnh && window.jpnh.openExternal) {
              window.jpnh.openExternal("file://" + d.savePath);
            }
          });
          item.appendChild(openBtn);
        }

        const removeBtn = el("button", "btn small ghost", "\u2715");
        removeBtn.addEventListener("click", () => removeDownload(d.id));
        item.appendChild(removeBtn);
      }

      listEl.appendChild(item);
    });
  }

  function getBarElement() {
    create();
    return barEl;
  }

  return { show, hide, addDownload, updateProgress, complete, clearAll, getBarElement };
})();
