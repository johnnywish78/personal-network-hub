"use strict";

// JPNH Icon System — navigation SVG icons, brand PNG helper, utility icons.

window.JpnhIcons = (function () {

  // ── Navigation Icons ──────────────────────────────────────────────────
  // Each icon is an SVG with viewBox="0 0 24 24", designed to be colorful
  // and meaningful. Colors are embedded for a polished look.
  // Size: 22px for clear visibility in sidebar.

  const navIcons = {
    // Dashboard — grid of squares
    dashboard: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none"><rect x="3" y="3" width="8" height="8" rx="2" fill="#60a5fa"/><rect x="13" y="3" width="8" height="8" rx="2" fill="#34d399"/><rect x="3" y="13" width="8" height="8" rx="2" fill="#fbbf24"/><rect x="13" y="13" width="8" height="8" rx="2" fill="#f472b6"/></svg>`,

    // Browser — globe with ring
    browser: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#60a5fa" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M2 12h20"/><path d="M12 3a14 14 0 0 1 3 9 14 14 0 0 1-3 9 14 14 0 0 1-3-9 14 14 0 0 1 3-9z" fill="none"/></svg>`,

    // Services — stacked server racks
    services: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none"><rect x="3" y="2" width="18" height="7" rx="2" fill="#34d399"/><rect x="3" y="15" width="18" height="7" rx="2" fill="#34d399"/><circle cx="7" cy="5.5" r="1.2" fill="#fff"/><circle cx="7" cy="18.5" r="1.2" fill="#fff"/><rect x="12" y="4" width="5" height="2" rx="1" fill="#fff" opacity=".5"/><rect x="12" y="17" width="5" height="2" rx="1" fill="#fff" opacity=".5"/></svg>`,

    // Network Checker — magnifying glass with pulse
    checker: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round"><circle cx="10" cy="10" r="7"/><path d="M15.5 15.5L21 21"/><path d="M7 10h6"/><path d="M10 7v6" stroke-width="1.8"/></svg>`,

    // Network — connected nodes
    network: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke-linecap="round"><circle cx="12" cy="5" r="2.5" fill="#a78bfa" stroke="#a78bfa" stroke-width="1.5"/><circle cx="5" cy="19" r="2.5" fill="#f472b6" stroke="#f472b6" stroke-width="1.5"/><circle cx="19" cy="19" r="2.5" fill="#38bdf8" stroke="#38bdf8" stroke-width="1.5"/><path d="M12 7.5v4" stroke="#a78bfa" stroke-width="1.5"/><path d="M7.2 17L10 13" stroke="#f472b6" stroke-width="1.5"/><path d="M16.8 17L14 13" stroke="#38bdf8" stroke-width="1.5"/></svg>`,

    // Configs — slider controls
    configs: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke-width="2" stroke-linecap="round"><line x1="4" y1="6" x2="20" y2="6" stroke="#fb923c"/><line x1="4" y1="12" x2="20" y2="12" stroke="#fb923c"/><line x1="4" y1="18" x2="20" y2="18" stroke="#fb923c"/><circle cx="8" cy="6" r="2.5" fill="#fb923c" stroke="none"/><circle cx="16" cy="12" r="2.5" fill="#fb923c" stroke="none"/><circle cx="10" cy="18" r="2.5" fill="#fb923c" stroke="none"/></svg>`,

    // Updates — circular arrows
    updates: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#2dd4bf" stroke-width="2" stroke-linecap="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>`,

    // Clients — monitor with user
    clients: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#818cf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" fill="#818cf8" fill-opacity=".15"/><path d="M8 21h8"/><path d="M12 17v4"/><circle cx="12" cy="10" r="3" fill="#818cf8" fill-opacity=".3"/></svg>`,

    // Settings — gear
    settings: `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#94a3b8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
  };

  // ── Utility Icons ─────────────────────────────────────────────────────
  // Size: 18px for clear visibility in topbar.

  const sun = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4" fill="#f59e0b" fill-opacity=".2"/><line x1="12" y1="1" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;

  const moon = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="#818cf8" stroke-width="2" stroke-linecap="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" fill="#818cf8" fill-opacity=".15"/></svg>`;

  const refresh = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>`;

  // ── Brand PNG Helper ──────────────────────────────────────────────────

  // Real PNG logos live under assets/icons/. Returns an <img> tag string.
  // scale: optional CSS transform scale to zoom into the logo content area,
  // compensating for transparent padding in some PNGs (e.g. GitHub).
  function brandImg(name, size, scale) {
    const s = size || 32;
    const src = `assets/icons/${name}.png`;
    const scaleCss = scale ? `transform:scale(${scale});` : "";
    return `<img src="${src}" width="${s}" height="${s}" alt="${name}" style="object-fit:contain;flex-shrink:0;${scaleCss}" />`;
  }

  // ── Public API ────────────────────────────────────────────────────────

  function navIcon(key, size) {
    const svg = navIcons[key];
    if (!svg) return "";
    if (size && size !== 22) {
      return svg.replace('width="22" height="22"', `width="${size}" height="${size}"`);
    }
    return svg;
  }

  return {
    navIcon,
    brandImg,
    nav: navIcons,
    utility: { sun, moon, refresh },
  };
})();
