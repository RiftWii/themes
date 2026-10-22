# SPDX-FileCopyrightText: 2026 RiftWii contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for previews: validate_theme.py rejects a preview.png, and
build_index.py publishes a preview for every theme.

    python3 -I -m unittest discover -s tests
"""

import io
import json
import sys
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

from png_helpers import make_png, temp_dir, write_stub_theme_check, write_theme

import build_index
import validate_theme


def validate(files):
    """(errors, warnings, output) for a theme holding `files`."""
    with temp_dir() as tmp:
        write_theme(Path(tmp) / "themes", "Test", files)
        theme_check = write_stub_theme_check(tmp)
        report = validate_theme.Report()
        output = io.StringIO()
        with redirect_stdout(output):
            validate_theme.validate_theme(
                Path(tmp) / "themes" / "Test", validate_theme.load_image_sizes(theme_check),
                theme_check, {}, {}, report)
        return report.errors, report.warnings, output.getvalue()


class PreviewValidation(unittest.TestCase):
    def test_preview_png_is_rejected_with_a_clear_message(self):
        errors, _, output = validate({"preview.png": make_png(640, 480)})
        self.assertEqual(errors, 1, output)
        self.assertIn("preview.png is no longer used: every theme gets a drawn preview of "
                      "RiftWii's Home. Remove it from the folder.", output)

    def test_any_preview_png_is_rejected_without_being_read(self):
        # Not a PNG at all: still one clear message, not a PNG complaint.
        errors, _, output = validate({"preview.png": b"GIF89a" + bytes(100)})
        self.assertEqual(errors, 1, output)
        self.assertIn("no longer used", output)
        self.assertNotIn("not a PNG", output)

    def test_theme_without_preview_passes(self):
        errors, warnings, output = validate({})
        self.assertEqual((errors, warnings), (0, 0), output)


class PreviewPublishing(unittest.TestCase):
    def build(self, files):
        """(themes.json entry, preview bytes or None, zip names, unpacked size)."""
        with temp_dir() as tmp:
            themes = Path(tmp) / "themes"
            write_theme(themes, "Test", files)
            theme_check = write_stub_theme_check(tmp)
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
            preview_file = site / "previews" / "Test.png"
            preview = preview_file.read_bytes() if preview_file.is_file() else None
            with zipfile.ZipFile(site / "themes" / "Test.zip") as archive:
                names = sorted(archive.namelist())
                unpacked = sum(info.file_size for info in archive.infolist())
            return entry, preview, names, unpacked

    def test_preview_url_stays_the_same_and_zip_counts_match(self):
        entry, preview, names, unpacked = self.build({"background.png": make_png(640, 480, colour=(9, 9, 9))})
        self.assertIsNotNone(preview)
        self.assertIn("Test/background.png", names)
        self.assertEqual(entry["preview"], "https://example.test/previews/Test.png")
        # What the Wii's installer compares the zip with.
        self.assertEqual(entry["files"], len(names))
        self.assertEqual(entry["unpacked_size"], unpacked)

    def test_background_is_the_fallback(self):
        background = make_png(640, 480, colour=(9, 9, 9))
        entry, preview, names, unpacked = self.build({"background.png": background})
        self.assertEqual(preview, background)
        self.assertEqual(entry["files"], len(names))
        self.assertEqual(entry["unpacked_size"], unpacked)

    def test_no_picture_means_no_preview(self):
        entry, preview, _, _ = self.build({})
        self.assertIsNone(preview)
        self.assertIsNone(entry["preview"])


if __name__ == "__main__":
    unittest.main()
