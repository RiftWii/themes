#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RiftWii contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws the example theme's pictures (themes/Tidepool), from nothing but
arithmetic, so their origin is plain: no source images, no fonts.

    make_example_theme.py themes/Tidepool

The pictures this script writes are CC0 (themes/Tidepool/LICENSE); the
script itself is GPL-3.0-or-later like the rest of scripts/.
Standard library only.
"""

import math
import struct
import sys
import zlib
from pathlib import Path

# Tidepool's colours, the same as its theme.ini.
DEEP = (14, 58, 71)
SHALLOW = (38, 112, 122)
FOAM = (214, 236, 232)
CARD = (246, 241, 230)       # sand
ACCENT = (240, 160, 92)      # coral
SHADOW = (6, 30, 38)


def write_png(path, width, height, pixel):
    """pixel(x, y) -> (r, g, b, a). Writes an 8-bit RGBA PNG."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # filter type 0 (none) on every row
        for x in range(width):
            rows.extend(pixel(x, y))

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b"")
    Path(path).write_bytes(data)


def mix(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def clamp01(v):
    return max(0.0, min(1.0, v))


def rounded_rect_distance(x, y, left, top, right, bottom, radius):
    """Signed distance from pixel centre (x+0.5, y+0.5) to a rounded
    rectangle: negative inside. Used for smooth (anti-aliased) edges."""
    px, py = x + 0.5, y + 0.5
    cx, cy = (left + right) / 2, (top + bottom) / 2
    half_w, half_h = (right - left) / 2 - radius, (bottom - top) / 2 - radius
    dx, dy = abs(px - cx) - half_w, abs(py - cy) - half_h
    outside = math.hypot(max(dx, 0), max(dy, 0))
    inside = min(max(dx, dy), 0)
    return outside + inside - radius


def background(x, y):
    # Deep water at the top, lighter towards the bottom, with slow swells.
    # The left and right edges are plain gradient so RiftWii's mirroring on
    # wider screens (docs/THEMES.md) looks like more of the same.
    t = y / 479
    swell = 0.5 + 0.5 * math.sin(x / 640 * math.pi * 2 + y / 38.0)
    edge_fade = min(1.0, min(x, 639 - x) / 120)
    t = clamp01(t + 0.035 * swell * edge_fade)
    r, g, b = mix(DEEP, SHALLOW, t)
    return (r, g, b, 255)


def tile(lit):
    # The card body where RiftWii's own tile has it (7,7)-(131,91), with a
    # soft shadow below and, lit, a coral ring in the glow margin.
    def pixel(x, y):
        body = rounded_rect_distance(x, y, 7, 7, 131, 91, 12)
        shadow = rounded_rect_distance(x, y - 2, 7, 7, 131, 91, 12)
        shadow_alpha = clamp01(1 - shadow / 5) * 0.35
        color, alpha = SHADOW, shadow_alpha
        if lit:
            ring = clamp01(1 - abs(body - 3) / 2.5)
            if ring > alpha:
                color, alpha = ACCENT, ring
        cover = clamp01(0.5 - body)
        if cover > 0:
            # A little foam along the top edge of the sand.
            sand = mix(FOAM, CARD, clamp01((y - 7) / 10))
            color = mix(color, sand, cover) if alpha > 0 else sand
            alpha = cover + alpha * (1 - cover)
        return (*color, round(alpha * 255))
    return pixel


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[1])
    write_png(out / "background.png", 640, 480, background)
    write_png(out / "tile.png", 140, 100, tile(lit=False))
    write_png(out / "tile_over.png", 140, 100, tile(lit=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
