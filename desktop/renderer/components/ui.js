"use strict";

// Shared UI helpers: cards, badges, status dots, toasts, modals, tables.

window.ui = (function () {
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text instanceof Node) {
      node.appendChild(text);
    } else if (Array.isArray(text)) {
      text.forEach((child) => {
        if (child instanceof Node) node.appendChild(child);
      });
    } else if (text !== undefined && text !== null) {
      node.textContent = String(text);
    }
    return node;
  }

  function statusClass(status) {
    const s = String(status || "").toUpperCase();
    if (["OK", "WORKING", "PASS", "ONLINE", "SUCCESS", "CONFIGURED", "DETECTED", "INSTALLED"].includes(s)) return "ok";
    if (["DEGRADED", "PARTIAL", "WARNING"].includes(s)) return "warn";
    if (["FAILED", "FAIL", "ERROR", "OFFLINE", "TIMEOUT"].includes(s)) return "bad";
    return "muted";
  }

  function statusDot(status) {
    const dot = el("span", `dot ${statusClass(status)}`);
    dot.title = status || "";
    return dot;
  }

  function badge(text, status) {
    return el("span", `badge ${statusClass(status)}`, text);
  }

  function card(title, body, actions) {
    const wrap = el("section", "card");
    if (title) {
      const head = el("div", "card-head");
      head.appendChild(el("h3", "card-title", title));
      if (actions) head.appendChild(actions);
      wrap.appendChild(head);
    }
    wrap.appendChild(el("div", "card-body", null));
    if (body instanceof Node) wrap.lastChild.appendChild(body);
    else if (Array.isArray(body)) body.forEach((n) => wrap.lastChild.appendChild(n));
    wrap._setBody = (content) => {
      const items = Array.isArray(content) ? content : [content];
      wrap.lastChild.replaceChildren(...items);
    };
    return wrap;
  }

  function toast(message, kind = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = el("div", "toast-container");
      container.id = "toast-container";
      document.body.appendChild(container);
    }
    const item = el("div", `toast ${kind}`, message);
    container.appendChild(item);
    setTimeout(() => {
      item.classList.add("fade");
      setTimeout(() => item.remove(), 300);
    }, 3200);
  }

  function openModal(title, body, buttons = []) {
    const overlay = el("div", "modal-overlay");
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeModal(overlay);
    });
    const box = el("div", "modal");
    const head = el("div", "modal-head");
    head.appendChild(el("h3", null, title));
    const closeBtn = el("button", "btn ghost", "×");
    closeBtn.addEventListener("click", () => closeModal(overlay));
    head.appendChild(closeBtn);
    box.appendChild(head);
    const content = el("div", "modal-body");
    if (body instanceof Node) content.appendChild(body);
    else if (Array.isArray(body)) body.forEach((n) => content.appendChild(n));
    else if (typeof body === "string") content.appendChild(el("p", null, body));
    box.appendChild(content);
    const foot = el("div", "modal-foot");
    buttons.forEach((b) => {
      const btn = el("button", `btn ${b.kind || "primary"}`, b.label);
      btn.addEventListener("click", () => b.onClick(overlay, btn));
      foot.appendChild(btn);
    });
    box.appendChild(foot);
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    return overlay;
  }

  function closeModal(overlay) {
    overlay && overlay.remove();
  }

  function confirmDialog(title, message, onConfirm) {
    openModal(title, message, [
      { label: "Cancel", kind: "ghost", onClick: (o) => closeModal(o) },
      {
        label: "Confirm",
        kind: "danger",
        onClick: (o) => {
          closeModal(o);
          onConfirm();
        },
      },
    ]);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).then(() => true);
    }
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return Promise.resolve(ok);
  }

  function field(labelText, input) {
    const wrap = el("label", "field");
    wrap.appendChild(el("span", "field-label", labelText));
    wrap.appendChild(input);
    return wrap;
  }

  function table(headers, rows) {
    const t = el("table", "table");
    const thead = el("thead");
    const tr = el("tr");
    headers.forEach((h) => tr.appendChild(el("th", null, h)));
    thead.appendChild(tr);
    t.appendChild(thead);
    const tbody = el("tbody");
    rows.forEach((row) => {
      const r = el("tr");
      row.forEach((cell) => {
        const td = el("td");
        if (cell instanceof Node) td.appendChild(cell);
        else td.textContent = cell == null ? "-" : String(cell);
        r.appendChild(td);
      });
      tbody.appendChild(r);
    });
    t.appendChild(tbody);
    return t;
  }

  function spinner() {
    return el("span", "spinner");
  }

  function openExternal(url) {
    if (!url) return;
    if (window.jpnh && window.jpnh.openExternal) {
      window.jpnh.openExternal(url);
    } else if (window.open) {
      window.open(url, "_blank");
    }
  }

  // ---- Embedded browser (Browser Hub) ----
  function openPanel(url) {
    return openBrowser(url);
  }

  function openBrowser(url, title) {
    if (!url) return;
    if (!/^https?:\/\//i.test(url)) {
      toast(`Cannot open non-HTTP URL embedded: ${url}`, "warn");
      openExternal(url);
      return;
    }
    if (window.BrowserHub && window.BrowserHub.queueOpen) {
      window.BrowserHub.queueOpen(url, title || url);
      return;
    }
    openExternal(url);
  }

  return {
    el, statusClass, statusDot, badge, card, toast, openModal, closeModal,
    confirmDialog, copyText, field, table, spinner, openExternal, openPanel, openBrowser,
  };
})();
