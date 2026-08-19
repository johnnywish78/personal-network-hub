#!/usr/bin/env python3
"""Generate the JPNH app icon set from the jpnh-master image.

Produces:
  assets/icons/icon.png           1024x1024 master (Linux/Electron window icon)
  assets/icons/icon.ico           multi-resolution Windows .ico
  assets/icons/png/{16,32,48,64,128,256,512}.png  Linux size set

Source: assets/icons/jpnh-master.png (the user's chosen app icon). The image
is center-cropped to a square and masked to a CIRCLE so it reads as a round
app icon at every size. If jpnh-master.png is missing, the user avatar
(desktop/renderer/assets/avatar.jpg) is used, and finally a generated
"network hub" mark as a last-resort fallback.

Note: the avatar used INSIDE the app (renderer/assets/avatar.jpg) is
independent and is not modified by this script.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "icons"
MASTER_IMG = OUT / "jpnh-master.png"
AVATAR = ROOT / "desktop" / "renderer" / "assets" / "avatar.jpg"

BG_TOP = (27, 33, 43, 255)
BG_BOTTOM = (14, 17, 22, 255)
ACCENT = (79, 140, 255, 255)
ACCENT_LIGHT = (124, 171, 255, 255)
ACCENT_DIM = (43, 75, 134, 255)
NODE = (155, 167, 189, 255)

MASTER = 1024


def center_crop_to_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def circular_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([0, 0, size - 1, size - 1], fill=255)
    return mask


def avatar_icon(size: int, source: Image.Image) -> Image.Image:
    square = center_crop_to_square(source.convert("RGB"))
    square = square.resize((size, size), Image.LANCZOS)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = circular_mask(size)
    canvas.paste(square, (0, 0), mask)
    return canvas


def fallback_icon(size: int) -> Image.Image:
    """The original drawn "network hub" mark (used when the avatar is absent)."""
    f = size / 4096
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / max(1, size - 1)
        c = tuple(round(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(4))
        gd.line([(0, y), (size, y)], fill=c)
    radius = round(200 * f)
    mask = rounded_mask(size, radius)
    canvas.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(canvas)
    cx = cy = size / 2
    ring_r = round(236 * f)
    sat_r = round(110 * f)
    hub_r = round(190 * f)
    hub_core = round(104 * f)

    d.ellipse([cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
              outline=ACCENT_DIM, width=max(1, round(26 * f)))
    for i in range(6):
        angle = math.radians(60 * i - 90)
        sx = cx + math.cos(angle) * ring_r
        sy = cy + math.sin(angle) * ring_r
        d.line([(cx, cy), (sx, sy)], fill=ACCENT_DIM, width=max(1, round(30 * f)))
    for i in range(6):
        angle = math.radians(60 * i - 90)
        sx = cx + math.cos(angle) * ring_r
        sy = cy + math.sin(angle) * ring_r
        d.ellipse([sx - sat_r, sy - sat_r, sx + sat_r, sy + sat_r],
                  fill=(20, 26, 34, 255))
        d.ellipse([sx - sat_r, sy - sat_r, sx + sat_r, sy + sat_r],
                  outline=NODE, width=max(1, round(16 * f)))
        d.ellipse([sx - round(46 * f), sy - round(46 * f),
                   sx + round(46 * f), sy + round(46 * f)], fill=NODE)
    d.ellipse([cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r], fill=ACCENT)
    d.ellipse([cx - hub_core, cy - hub_core, cx + hub_core, cy + hub_core],
              fill=ACCENT_LIGHT)
    return canvas


def _icon_source() -> Image.Image:
    for candidate in (MASTER_IMG, AVATAR):
        if candidate.exists():
            return Image.open(candidate)
    return None


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    png_dir = OUT / "png"
    png_dir.mkdir(parents=True, exist_ok=True)

    source_img = _icon_source()
    source_name = MASTER_IMG.name if MASTER_IMG.exists() else (AVATAR.name if AVATAR.exists() else "fallback-mark")
    if source_img is None:
        master = fallback_icon(MASTER)
    else:
        master = avatar_icon(MASTER, source_img)

    master.save(OUT / "icon.png")

    for s in (512, 256, 128, 64, 48, 32, 16):
        master.resize((s, s), Image.LANCZOS).save(png_dir / f"{s}.png")

    master.resize((256, 256), Image.LANCZOS).save(
        OUT / "icon.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    print(f"Icons written to {OUT} (source: {source_name})")
    for p in sorted(OUT.rglob("*")):
        if p.is_file() and p.name != "jpnh-master.jpg":
            print(f"  {p.relative_to(OUT)}  {p.stat().st_size} bytes")


if __name__ == "__main__":
    main()