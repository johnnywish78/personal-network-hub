"use strict";

const { Menu, clipboard, shell } = require("electron");

function buildTemplate(ctx) {
  const items = [];

  if (ctx.linkURL) {
    items.push(
      { label: "Open link in new tab", click: "open-link-new-tab", linkURL: ctx.linkURL },
      { label: "Open link in new window", click: "open-link-new-window", linkURL: ctx.linkURL },
      { type: "separator" },
      { label: "Copy link address", click: "copy-link", linkURL: ctx.linkURL }
    );
    items.push({ type: "separator" });
  }

  if (ctx.mediaType === "image" && ctx.srcURL) {
    items.push(
      { label: "Open image in new tab", click: "open-image-new-tab", srcURL: ctx.srcURL },
      { label: "Save image as...", click: "save-image", srcURL: ctx.srcURL },
      { label: "Copy image", click: "copy-image", srcURL: ctx.srcURL },
      { label: "Copy image address", click: "copy-image-address", srcURL: ctx.srcURL }
    );
    items.push({ type: "separator" });
  }

  if (ctx.hasText) {
    items.push(
      { label: "Copy", click: "copy", text: ctx.selectionText },
      { type: "separator" }
    );
  }

  if (ctx.isEditable) {
    items.push(
      { label: "Undo", role: "undo" },
      { label: "Redo", role: "redo" },
      { type: "separator" },
      { label: "Cut", role: "cut" },
      { label: "Copy", role: "copy" },
      { label: "Paste", role: "paste" },
      { label: "Select All", role: "selectAll" }
    );
    items.push({ type: "separator" });
  }

  items.push(
    { label: "Back", click: "go-back", enabled: ctx.canGoBack },
    { label: "Forward", click: "go-forward", enabled: ctx.canGoForward },
    { label: "Reload", click: "reload" },
    { type: "separator" },
    { label: "Save page as...", click: "save-page" },
    { label: "Print...", click: "print" },
    { type: "separator" },
    { label: "View page source", click: "view-source" },
    { label: "Inspect element", click: "inspect" }
  );

  return items;
}

function show(mainWindow, webviewId, ctx) {
  const template = buildTemplate(ctx);
  const menu = Menu.buildFromTemplate(
    template.map((item) => {
      if (item.role) return { role: item.role };
      return {
        label: item.label,
        enabled: item.enabled !== false,
        click: () => {
          mainWindow.webContents.send("context-menu-action", {
            action: item.click,
            webviewId,
            linkURL: item.linkURL,
            srcURL: item.srcURL,
            text: item.text,
          });
        },
      };
    })
  );
  menu.popup({ window: mainWindow });
}

module.exports = { show };
