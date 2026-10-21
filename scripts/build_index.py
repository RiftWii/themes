#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RiftWii contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Builds the GitHub Pages site: one zip per theme and themes.json.

    build_index.py --theme-check BIN --themes themes --out site [--base-url URL]

The base URL the zips and previews are served under comes from
site-url.txt at the repository's root, the one place it is written down;
--base-url overrides it for a local test.

Run it only on themes that passed validate_theme.py (publish.yml does both).

site/themes/<folder>.zip   the theme, its files under "<folder>/"
site/previews/<folder>.png a preview picture, when the theme has one
site/themes.json           the list RiftWii (in future) and the themes page browse
site/index.html            a redirect to the themes page on the main website

The zips are deterministic: entries sorted by name, a fixed 1980-01-01
timestamp, fixed permissions and a fixed compression level, so the same
files give the same bytes and the same SHA-256 on every publish (with the
same zlib). A theme's hash then only changes when the theme does.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

# Run with "python3 -I", which leaves the script's own folder off the path.
sys.dont_write_bytecode = True  # keep __pycache__ out of the checkout
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_theme import PREVIEW_NAME, parse_ini_with_riftwii, read_license  # noqa: E402

INDEX_SCHEMA = 1
SITE_URL_FILE = Path(__file__).resolve().parent.parent / "site-url.txt"
SITE_PAGE = Path(__file__).resolve().parent.parent / "web" / "index.html"
ZIP_DATE = (1980, 1, 1, 0, 0, 0)  # the earliest date a zip can store


def build_zip(theme_dir, zip_path):
    """Writes the theme's zip and returns (file count, unpacked bytes)."""
    # preview.png is for the website, not the Wii, so it stays out.
    names = sorted(entry.name for entry in theme_dir.iterdir() if entry.is_file() and entry.name != PREVIEW_NAME)
    unpacked = 0
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name in names:
            data = (theme_dir / name).read_bytes()
            unpacked += len(data)
            info = zipfile.ZipInfo(f"{theme_dir.name}/{name}", date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3              # Unix, whatever OS builds it
            info.external_attr = 0o100644 << 16  # a plain rw-r--r-- file
            archive.writestr(info, data, compresslevel=9)
    return len(names), unpacked


def sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--theme-check", required=True)
    parser.add_argument("--themes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--base-url", help="where the site is served; default: site-url.txt")
    args = parser.parse_args()

    base_url = args.base_url or SITE_URL_FILE.read_text(encoding="utf-8").strip()
    base_url = base_url.rstrip("/") + "/"
    (args.out / "themes").mkdir(parents=True, exist_ok=True)
    (args.out / "previews").mkdir(parents=True, exist_ok=True)

    entries = []
    theme_dirs = sorted(path for path in args.themes.iterdir() if path.is_dir()) if args.themes.is_dir() else []
    for theme_dir in theme_dirs:
        folder = theme_dir.name
        name, author, _notes = parse_ini_with_riftwii(args.theme_check, theme_dir / "theme.ini")
        license_fields = read_license((theme_dir / "LICENSE").read_text(encoding="utf-8"))

        zip_path = args.out / "themes" / f"{folder}.zip"
        file_count, unpacked = build_zip(theme_dir, zip_path)

        # The submitter's own screenshot (preview.png) when there is one,
        # else the theme's background. A rendered menu screen would be
        # better, but RiftWii's theme kit (tools/theme_kit.cpp) paints
        # single pictures, not whole screens.
        preview = None
        for candidate in (PREVIEW_NAME, "background.png"):
            if (theme_dir / candidate).is_file():
                shutil.copyfile(theme_dir / candidate, args.out / "previews" / f"{folder}.png")
                preview = f"{base_url}previews/{folder}.png"
                break

        entries.append({
            "folder": folder,
            "name": name or folder,
            "author": author,
            "license": license_fields.get("license", ""),
            "size": zip_path.stat().st_size,
            "sha256": sha256_of(zip_path),
            "files": file_count,
            "unpacked_size": unpacked,
            "has_music": (theme_dir / "music.ogg").is_file(),
            "zip": f"{base_url}themes/{folder}.zip",
            "preview": preview,
        })
        print(f"{folder}: {entries[-1]['size']} bytes, sha256 {entries[-1]['sha256']}")

    index = {
        "schema": INDEX_SCHEMA,
        # The commit the site was built from, not a timestamp, so building
        # the same commit twice gives the same file.
        "commit": os.environ.get("GITHUB_SHA", ""),
        "themes": entries,
    }
    (args.out / "themes.json").write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out / 'themes.json'} with {len(entries)} theme(s)")

    # People who open the site in a browser are sent on to the themes page
    # of the main RiftWii website (web/index.html is only that redirect).
    shutil.copyfile(SITE_PAGE, args.out / "index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
