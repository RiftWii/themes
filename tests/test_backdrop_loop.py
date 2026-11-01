# SPDX-FileCopyrightText: 2026 RiftWii contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for looping backdrops: validate_theme.py accepts backdrop_NN.png
frames a theme.ini's [backdrop] frames asks for, and fails a loop RiftWii
would refuse to play.

    python3 -I -m unittest discover -s tests
"""

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from png_helpers import make_png, temp_dir, write_theme

import validate_theme

# A theme_check that answers "loop" from the theme.ini's [backdrop] frames
# and fps, as RiftWii's parse_theme() does for sensible values.
STUB_THEME_CHECK_WITH_LOOP = r"""#!/usr/bin/env python3
import sys
if sys.argv[1] == "images":
    print("background 640 480\ntile 140 100")
    raise SystemExit
frames, fps, section = 0, 12, ""
for line in open(sys.argv[2], encoding="utf-8"):
    line = line.strip()
    if line.startswith("["):
        section = line.strip("[]")
    elif section == "backdrop" and "=" in line:
        key, value = (part.strip() for part in line.split("=", 1))
        if key == "frames":
            frames = int(value)
        elif key == "fps":
            fps = int(value)
print("name\tTest theme\nauthor\tTester")
print("loop\t%d\t%d" % (frames, fps))
"""


def validate(files, frames=None):
    """(errors, warnings, output) for a theme holding `files`, its
    theme.ini asking for `frames` loop frames (None: no [backdrop])."""
    with temp_dir() as tmp:
        theme = write_theme(Path(tmp) / "themes", "Test", files)
        if frames is not None:
            (theme / "theme.ini").write_text(
                "[theme]\nname = Test theme\nauthor = Tester\n\n[backdrop]\nframes = %d\nfps = 12\n" % frames,
                encoding="utf-8")
        theme_check = Path(tmp) / "theme_check"
        theme_check.write_text(STUB_THEME_CHECK_WITH_LOOP, encoding="utf-8")
        theme_check.chmod(0o755)
        report = validate_theme.Report()
        output = io.StringIO()
        with redirect_stdout(output):
            validate_theme.validate_theme(
                theme, validate_theme.load_image_sizes(str(theme_check)), str(theme_check), {}, {}, report)
        return report.errors, report.warnings, output.getvalue()


def frames_of(count, width=64, height=48):
    files = {f"backdrop_{i:02d}.png": make_png(width, height) for i in range(count)}
    files["background.png"] = make_png(640, 480)
    return files


class BackdropLoop(unittest.TestCase):
    def test_a_good_loop_passes(self):
        errors, warnings, output = validate(frames_of(3), frames=3)
        self.assertEqual((errors, warnings), (0, 0), output)
        self.assertIn("OK themes/Test", output)

    def test_a_missing_frame_fails(self):
        files = frames_of(3)
        del files["backdrop_01.png"]
        errors, _, output = validate(files, frames=3)
        self.assertEqual(errors, 1, output)
        self.assertIn("backdrop_01.png: missing", output)

    def test_a_frame_of_another_size_fails(self):
        files = frames_of(3)
        files["backdrop_02.png"] = make_png(68, 48)
        errors, _, output = validate(files, frames=3)
        self.assertEqual(errors, 1, output)
        self.assertIn("not the 64x48 of backdrop_00.png", output)

    def test_a_size_not_a_multiple_of_four_fails(self):
        errors, _, output = validate(frames_of(2, 66, 48), frames=2)
        self.assertEqual(errors, 1, output)
        self.assertIn("multiples of 4", output)

    def test_a_loop_over_four_mebibytes_fails(self):
        # 6 frames of 856x480 are 4.7 MiB as RGB565.
        errors, _, output = validate(frames_of(6, 856, 480), frames=6)
        self.assertEqual(errors, 1, output)
        self.assertIn("the limit is 4 MiB", output)

    def test_a_frame_beyond_the_count_fails(self):
        errors, _, output = validate(frames_of(4), frames=3)
        self.assertEqual(errors, 1, output)
        self.assertIn("backdrop_03.png: a looping backdrop frame", output)

    def test_frames_without_a_loop_in_the_ini_fail(self):
        errors, _, output = validate(frames_of(2))
        self.assertEqual(errors, 2, output)
        self.assertIn("doesn't ask for", output)

    def test_a_loop_without_a_still_background_warns(self):
        files = frames_of(2)
        del files["background.png"]
        errors, warnings, output = validate(files, frames=2)
        self.assertEqual((errors, warnings), (0, 1), output)
        self.assertIn("no background.png", output)


if __name__ == "__main__":
    unittest.main()
