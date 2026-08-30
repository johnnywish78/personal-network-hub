"use strict";

window.FindBar = (function () {
  let barEl = null;
  let inputEl = null;
  let countEl = null;
  let activeFrame = null;
  let lastQuery = "";

  function create() {
    if (barEl) return;
    const { el } = window.ui;
    barEl = el("div", "find-bar hidden");

    const closeBtn = el("button", "btn small ghost", "\u2715");
    closeBtn.title = "Close (Escape)";

    inputEl = el("input", "mono");
    inputEl.placeholder = "Find in page...";
    inputEl.type = "text";

    countEl = el("span", "find-count", "");

    const prevBtn = el("button", "btn small ghost", "\u25C0");
    prevBtn.title = "Previous (Shift+Enter)";
    const nextBtn = el("button", "btn small ghost", "\u25B6");
    nextBtn.title = "Next (Enter)";

    barEl.appendChild(closeBtn);
    barEl.appendChild(inputEl);
    barEl.appendChild(countEl);
    barEl.appendChild(prevBtn);
    barEl.appendChild(nextBtn);

    closeBtn.addEventListener("click", hide);
    prevBtn.addEventListener("click", findPrevious);
    nextBtn.addEventListener("click", findNext);

    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (e.shiftKey) findPrevious();
        else findNext();
      }
      if (e.key === "Escape") {
        e.preventDefault();
        hide();
      }
    });

    inputEl.addEventListener("input", () => {
      const q = inputEl.value;
      if (q !== lastQuery) {
        lastQuery = q;
        findInPage(q, false);
      }
    });
  }

  function show(frame) {
    create();
    activeFrame = frame;
    barEl.classList.remove("hidden");
    inputEl.value = "";
    countEl.textContent = "";
    inputEl.focus();
    inputEl.select();
  }

  function hide() {
    if (barEl) barEl.classList.add("hidden");
    if (activeFrame && activeFrame.stopFindInPage) {
      activeFrame.stopFindInPage("clearSelection");
    }
    activeFrame = null;
    lastQuery = "";
  }

  function findNext() {
    const q = inputEl ? inputEl.value : "";
    if (!q || !activeFrame) return;
    activeFrame.findInPage(q, { forward: true, findNext: true });
  }

  function findPrevious() {
    const q = inputEl ? inputEl.value : "";
    if (!q || !activeFrame) return;
    activeFrame.findInPage(q, { forward: false, findNext: true });
  }

  function findInPage(query, forward) {
    if (!activeFrame || !query) {
      if (countEl) countEl.textContent = "";
      return;
    }
    activeFrame.findInPage(query, { forward: forward !== false });
  }

  function updateCount(activeMatchOrdinal, matches) {
    if (countEl && matches > 0) {
      countEl.textContent = activeMatchOrdinal + "/" + matches;
    } else if (countEl) {
      countEl.textContent = "No results";
    }
  }

  function getBarElement() {
    create();
    return barEl;
  }

  function isVisible() {
    return barEl && !barEl.classList.contains("hidden");
  }

  return { show, hide, findNext, findPrevious, updateCount, getBarElement, isVisible };
})();
