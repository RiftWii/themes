# SPDX-FileCopyrightText: 2026 RiftWii contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for the mock preview: scripts/mock_preview.py and the order
build_index.py tries previews in (the mock, else the background).

    python3 -I -m unittest discover -s tests

Needs Pillow (scripts/requirements-preview.txt); without it these tests are
skipped, as build_index.py skips drawing and keeps the background.
"""

import io
import json
import struct
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from png_helpers import SCRIPTS, make_png, temp_dir, write_stub_theme_check, write_theme

try:
    from PIL import Image
    import mock_preview
except ImportError:  # no Pillow
    Image = mock_preview = None

import build_index

REPO = SCRIPTS.parent


def render(theme_dir, tmp):
    theme_check = write_stub_theme_check(tmp, with_look=True)
    return mock_preview.render_mock(theme_dir, theme_check)


@unittest.skipUnless(mock_preview, "Pillow is not installed")
class MockRender(unittest.TestCase):
    def test_indigo_and_cyan_render(self):
        for folder in ("Indigo", "Cyan"):
            with self.subTest(folder), temp_dir() as tmp:
                theme = REPO / "themes" / folder
                mock = render(theme, tmp)
                self.assertEqual(mock.size, (640, 480))
                self.assertEqual(mock.mode, "RGB")
                background = Image.open(theme / "background.png").convert("RGB")
                self.assertNotEqual(mock.tobytes(), background.tobytes(), "the mock should add Home's parts")
                # The top left corner is just the theme's background.
                self.assertEqual(mock.getpixel((2, 2)), background.getpixel((2, 2)))

    def test_theme_with_only_colors_renders(self):
        with temp_dir() as tmp:
            theme = write_theme(Path(tmp) / "themes", "Plain", {})
            (theme / "theme.ini").write_text(
                "[theme]\nname = Plain\nauthor = T\n[backdrop]\nstripes = no\n"
                "[colors]\nbackdrop = #102030\nbar = #405060\naccent = #FF8800\ncard = #EEEEEE\n", encoding="utf-8")
            mock = render(theme, tmp)
            self.assertEqual(mock.size, (640, 480))
            self.assertEqual(mock.getpixel((2, 2)), (0x10, 0x20, 0x30))  # the backdrop color, no stripes
            # The bar's body is near its color (shaded a little darker lower down).
            red, green, blue = mock.getpixel((320, 470))
            self.assertTrue(abs(red - 0x40) < 12 and abs(green - 0x50) < 12 and abs(blue - 0x60) < 12,
                            (red, green, blue))
            # The focused tile's outline is the accent.
            focused_left_edge = [mock.getpixel((x, 168)) for x in range(185, 200)]
            self.assertTrue(any(pixel[0] > 200 and pixel[2] < 80 for pixel in focused_left_edge))

    def test_stripes_are_drawn_when_on(self):
        with temp_dir() as tmp:
            theme = write_theme(Path(tmp) / "themes", "Striped", {})
            (theme / "theme.ini").write_text(
                "[theme]\nname = S\nauthor = T\n[colors]\nbackdrop = #102030\nbackdrop_stripe = #FF0000\n", encoding="utf-8")
            mock = render(theme, tmp)
            self.assertEqual(mock.getpixel((2, 2)), (255, 0, 0))   # y 2 and 3 are a stripe
            self.assertEqual(mock.getpixel((2, 4)), (0x10, 0x20, 0x30))

    def test_bumping_bar_renders(self):
        with temp_dir() as tmp:
            theme = write_theme(Path(tmp) / "themes", "Bump", {})
            (theme / "theme.ini").write_text("[theme]\nname = B\nauthor = T\n[shape]\nbar = bump\ncorners = 0\n",
                                             encoding="utf-8")
            self.assertEqual(render(theme, tmp).size, (640, 480))

    def test_pictures_of_the_wrong_size_or_a_huge_header_are_ignored(self):
        with temp_dir() as tmp:
            huge = make_png(640, 480)
            # Claim a 30000x30000 picture in the header; the data stays small.
            huge = huge[:16] + struct.pack(">II", 30000, 30000) + huge[24:]
            theme = write_theme(Path(tmp) / "themes", "Odd", {
                "tile.png": make_png(10, 10), "bar.png": huge, "background.png": b"not a png"})
            mock = render(theme, tmp)
            self.assertEqual(mock.size, (640, 480))

    def test_a_picture_over_the_pixel_limit_is_refused(self):
        with temp_dir() as tmp:
            # 2000x1200 solid color is a tiny file but 2.4 million pixels,
            # over mock_preview's limit (Pillow warns, load_picture refuses),
            # even though the caller expects exactly that size.
            theme = write_theme(Path(tmp) / "themes", "Big", {"background.png": make_png(2000, 1200)})
            self.assertIsNone(mock_preview.load_picture(theme, "background", (2000, 1200)))
            # And a size that doesn't match the expected one is skipped, too.
            self.assertIsNone(mock_preview.load_picture(theme, "background", (640, 480)))


@unittest.skipUnless(mock_preview, "Pillow is not installed")
class PreviewOrder(unittest.TestCase):
    def publish(self, files, with_look):
        with temp_dir() as tmp:
            themes = Path(tmp) / "themes"
            write_theme(themes, "Test", files)
            theme_check = write_stub_theme_check(tmp, with_look=with_look)
            site = Path(tmp) / "site"
            old_argv = sys.argv
            sys.argv = ["build_index.py", "--theme-check", theme_check, "--themes", str(themes),
                        "--out", str(site), "--base-url", "https://example.test/"]
            try:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(build_index.main(), 0)
            finally:
                sys.argv = old_argv
            entry = json.loads((site / "themes.json").read_text())["themes"][0]
            preview = site / "previews" / "Test.png"
            return entry, preview.read_bytes() if preview.is_file() else None

    def test_a_stray_preview_png_is_never_used(self):
        # validate_theme.py rejects it; if one got here anyway, the mock wins.
        screenshot = make_png(640, 480, colour=(1, 2, 3))
        _, preview = self.publish({"preview.png": screenshot, "background.png": make_png(640, 480)}, True)
        self.assertNotEqual(preview, screenshot)
        self.assertEqual(Image.open(io.BytesIO(preview)).size, (640, 480))

    def test_mock_is_drawn_for_every_theme(self):
        background = make_png(640, 480, colour=(9, 9, 9))
        entry, preview = self.publish({"background.png": background}, True)
        self.assertNotEqual(preview, background)
        self.assertEqual(Image.open(io.BytesIO(preview)).size, (640, 480))
        self.assertEqual(entry["preview"], "https://example.test/previews/Test.png")

    def test_a_theme_with_no_pictures_still_gets_a_preview(self):
        entry, preview = self.publish({}, True)
        self.assertIsNotNone(preview)
        self.assertIsNotNone(entry["preview"])

    def test_background_is_the_last_resort_when_drawing_fails(self):
        # This theme_check prints no colors, so the mock can't be drawn.
        background = make_png(640, 480, colour=(9, 9, 9))
        _, preview = self.publish({"background.png": background}, False)
        self.assertEqual(preview, background)


if __name__ == "__main__":
    unittest.main()
