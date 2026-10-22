# SPDX-FileCopyrightText: 2026 RiftWii contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Helpers the script tests share: tiny PNGs written with the standard
library, and a stand-in for the theme_check program.

The real theme_check is built from RiftWii's theme.cpp (scripts/
build_theme_check.sh). The tests don't need RiftWii's rules, only the two
answers the scripts ask of it, so a stub keeps them fast and offline.
"""

import struct
import sys
import tempfile
import zlib
from pathlib import Path

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def chunk(kind, body):
    crc = zlib.crc32(kind + body) & 0xFFFFFFFF
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)


def make_png(width, height, colour=(40, 90, 160), padding=0):
    """An 8-bit RGB PNG. `padding` bytes of tEXt are added, to reach a big
    file size without a big picture."""
    rows = bytearray()
    for _y in range(height):
        rows.append(0)  # filter: none
        for _x in range(width):
            rows += bytes(colour)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    text = chunk(b"tEXt", b"Comment\x00" + bytes(padding)) if padding else b""
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + text + chunk(b"IEND", b""))


def make_png_bomb(width=640, height=480, claimed_rows=40000):
    """A PNG whose header says 640x480 but whose zlib stream inflates to far
    more pixel data than that (about 77 MB from a few hundred KB)."""
    row = b"\x00" + bytes(width * 3)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(row * claimed_rows, 9)) + chunk(b"IEND", b""))


# A theme_check that answers like the real one for a theme with only a
# name and an author: "images" lists two pictures, "ini" prints the fields.
STUB_THEME_CHECK = """#!/bin/sh
case "$1" in
  images) printf 'background 640 480\\ntile 140 100\\n' ;;
  ini) printf 'name\\tTest theme\\nauthor\\tTester\\n' ;;
esac
"""


# The same, but also printing the settings the mock preview reads, like the
# real theme_check does: RiftWii's defaults (src/art/theme.cpp,
# ThemeColors) overlaid with the [colors] and [shape] keys the theme.ini
# sets. Only what the mock needs; the real one prints every colour key.
STUB_THEME_CHECK_WITH_LOOK = r"""#!/usr/bin/env python3
import sys
DEFAULTS = {
    "ink": "#2E2E36", "ink_soft": "#4A4A54", "ink_dim": "#6A6A74", "clock": "#74747E",
    "accent": "#2FB6E9", "glyph": "#55555F", "card": "#FFFFFF", "card_edge": "#CFCFD6",
    "card_edge_strong": "#C4C4CE", "shadow": "#28283C22", "glow": "#2FB6E950", "badge": "#ECECF1",
    "bar": "#DEDEE4", "backdrop": "#ECECEF", "backdrop_stripe": "#E3E3E8",
}
if sys.argv[1] == "images":
    print("background 640 480\ntile 140 100\ntile_empty 140 100\nbar 640 124")
    raise SystemExit
colors = dict(DEFAULTS)
shape = {"corners": "1", "stripes": "yes", "gloss": "no", "bar": "dip"}
section = ""
for line in open(sys.argv[2], encoding="utf-8"):
    line = line.strip()
    if line.startswith("["):
        section = line.strip("[]")
    elif "=" in line and not line.startswith("#"):
        key, value = (part.strip() for part in line.split("=", 1))
        if section == "colors":
            colors[key] = value
        elif section in ("shape", "backdrop"):
            shape[key] = value
print("name\tTest theme\nauthor\tTester")
print("corners\t" + shape["corners"])
print("stripes\t" + ("1" if shape["stripes"] == "yes" else "0"))
print("gloss\t" + ("1" if shape["gloss"] == "yes" else "0"))
print("bar\t" + shape["bar"])
for key, value in colors.items():
    print("color\t" + key + "\t" + value)
"""


def write_stub_theme_check(directory, with_look=False):
    path = Path(directory) / "theme_check"
    path.write_text(STUB_THEME_CHECK_WITH_LOOK if with_look else STUB_THEME_CHECK, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


def write_theme(themes_dir, folder, files):
    """themes_dir/folder with theme.ini and LICENSE, plus {name: bytes}."""
    theme = Path(themes_dir) / folder
    theme.mkdir(parents=True)
    (theme / "theme.ini").write_text("[theme]\nname = Test theme\nauthor = Tester\n", encoding="utf-8")
    (theme / "LICENSE").write_text("License: CC0-1.0\nAuthor: Tester\n", encoding="utf-8")
    for name, data in files.items():
        (theme / name).write_bytes(data)
    return theme


def temp_dir():
    return tempfile.TemporaryDirectory(prefix="themes-test-")
