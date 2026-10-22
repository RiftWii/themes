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


def write_stub_theme_check(directory):
    path = Path(directory) / "theme_check"
    path.write_text(STUB_THEME_CHECK, encoding="utf-8")
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
