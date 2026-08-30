"use strict";

window.ZoomControls = (function () {
  const ZOOM_LEVELS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4, 5];
  const DEFAULT_ZOOM = 1;
  let currentZoom = DEFAULT_ZOOM;
  let zoomLabelEl = null;

  function getZoom() {
    return currentZoom;
  }

  function setZoom(level) {
    level = Math.min(Math.max(level, 0.25), 5);
    currentZoom = Math.round(level * 100) / 100;
    updateLabel();
    return currentZoom;
  }

  function zoomIn() {
    const idx = ZOOM_LEVELS.findIndex((z) => z > currentZoom);
    if (idx !== -1) setZoom(ZOOM_LEVELS[idx]);
    else setZoom(ZOOM_LEVELS[ZOOM_LEVELS.length - 1]);
    return currentZoom;
  }

  function zoomOut() {
    let idx = ZOOM_LEVELS.length - 1;
    while (idx >= 0 && ZOOM_LEVELS[idx] >= currentZoom) idx--;
    if (idx >= 0) setZoom(ZOOM_LEVELS[idx]);
    else setZoom(ZOOM_LEVELS[0]);
    return currentZoom;
  }

  function reset() {
    setZoom(DEFAULT_ZOOM);
    return currentZoom;
  }

  function updateLabel() {
    if (zoomLabelEl) {
      zoomLabelEl.textContent = Math.round(currentZoom * 100) + "%";
    }
  }

  function createLabel() {
    const { el } = window.ui;
    zoomLabelEl = el("span", "zoom-level", Math.round(currentZoom * 100) + "%");
    return zoomLabelEl;
  }

  function render(parent) {
    const { el } = window.ui;
    const wrap = el("div", "zoom-controls");

    const outBtn = el("button", "btn small ghost", "\u2212");
    outBtn.title = "Zoom out (Ctrl+-)";
    outBtn.addEventListener("click", () => {
      if (window.BrowserHub && window.BrowserHub.applyZoomToActive) {
        window.BrowserHub.applyZoomToActive(zoomOut());
      }
    });

    const label = createLabel();

    const inBtn = el("button", "btn small ghost", "+");
    inBtn.title = "Zoom in (Ctrl++)";
    inBtn.addEventListener("click", () => {
      if (window.BrowserHub && window.BrowserHub.applyZoomToActive) {
        window.BrowserHub.applyZoomToActive(zoomIn());
      }
    });

    const resetBtn = el("button", "btn small ghost", "100%");
    resetBtn.title = "Reset zoom (Ctrl+0)";
    resetBtn.addEventListener("click", () => {
      if (window.BrowserHub && window.BrowserHub.applyZoomToActive) {
        window.BrowserHub.applyZoomToActive(reset());
      }
    });

    wrap.appendChild(outBtn);
    wrap.appendChild(label);
    wrap.appendChild(inBtn);
    wrap.appendChild(resetBtn);

    parent.appendChild(wrap);
    return wrap;
  }

  return { getZoom, setZoom, zoomIn, zoomOut, reset, render, updateLabel };
})();
