#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RiftWii contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Checks theme folders before they are merged or published.

    validate_theme.py --theme-check BIN [--flagged FILE] THEME_DIR...
    validate_theme.py --theme-check BIN [--flagged FILE] --all THEMES_DIR

THEME_DIR is one theme's folder (themes/<folder>). --all checks every
folder inside THEMES_DIR. BIN is scripts/theme_check built against
RiftWii's own src/art/theme.cpp (scripts/build_theme_check.sh), which gives
both the list of pictures RiftWii accepts and the theme.ini parser, so this
script never keeps its own copy of either.

Errors fail the run (exit 1). Warnings are for a person to look at: the
Nintendo-material checks only warn, because a word or a hash can't prove
where a file came from, and a reviewer decides.

Standard library only, so the Action needs no pip install, and it reads the
submitted files as data: nothing in a theme is imported or executed.
"""

import argparse
import hashlib
import os
import re
import stat
import struct
import subprocess
import sys
import wave
import zlib
from pathlib import Path

# --- Limits ----------------------------------------------------------------
#
# The first group copies what RiftWii itself enforces on the Wii
# (wii/menu/menutheme.cpp and docs/THEMES.md). A file over these is skipped
# there, so a theme that ships one would look broken to the player.
MAX_INI_BYTES = 64 * 1024          # kMaxIni: a bigger theme.ini is not read
MAX_PNG_BYTES = 2 * 1024 * 1024    # kMaxPng: a bigger picture is skipped
MAX_MUSIC_BYTES = 6 * 1024 * 1024  # music.ogg is loaded whole into memory
MAX_SOUND_BYTES = 1 * 1024 * 1024  # each sound effect WAV
MAX_SOUND_SECONDS = 5.0
SOUND_RATES = range(4000, 48000 + 1)
MUSIC_RATES = (44100, 48000)

# The second group is this repository's own choice (README.md, "Limits").
#
# Six minutes is what the 6 MB cap holds at the quality docs/THEMES.md
# recommends; a longer track only fits by lowering quality, and a reviewer
# has to listen to all of it.
MAX_MUSIC_SECONDS = 6 * 60
# 10 MiB per theme: the biggest music.ogg RiftWii plays (6 MiB) plus about
# twice Bookshelf's pictures (2.2 MiB), the largest bundled theme. It keeps
# a download on the Wii's slow Wi-Fi short and leaves room for about a
# hundred themes under GitHub Pages' 1 GB site limit.
MAX_THEME_BYTES = 10 * 1024 * 1024
MAX_LICENSE_BYTES = 64 * 1024
# preview.png is a screenshot for the website only: it is left out of the
# zip, so it never reaches a Wii, but it still counts towards the theme's
# size in the repository. A menu screenshot is 640x480.
PREVIEW_NAME = "preview.png"
PREVIEW_SIZE = (640, 480)
MAX_PREVIEW_BYTES = 1024 * 1024

# Folder names become zip names, URLs and folders on a FAT32 SD card.
# RiftWii's own update pack also allows spaces (theme_pack_name_ok in
# src/art/themepack.cpp); they are left out here so URLs need no escaping.
FOLDER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")

FIXED_FILES = {"theme.ini", "LICENSE"}
OPTIONAL_FILES = {"music.ogg", "hover.wav", "click.wav", "home_open.wav", "home_close.wav", PREVIEW_NAME}
REQUIRED_FILES = {"theme.ini", "LICENSE"}

# SPDX identifiers. Anything else needs the maintainers' approval, recorded
# in scripts/approved-licenses.txt so the approval is visible in history.
ALLOWED_LICENSES = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0"}

# Words that often mean a file came from Nintendo's software. Warnings
# only: "Wii" alone is everywhere in RiftWii themes, so it is not on here.
SUSPICIOUS_WORDS = re.compile(
    r"nintendo|ripped|\brip(?:s|ped)? from\b|extracted from|wii shop|mii channel|mii plaza"
    r"|totaka|system menu|\.brstm|\.brsar|\.tpl\b|\.arc\b",
    re.IGNORECASE,
)


# The notes src/art/theme.cpp writes for a section or key it doesn't
# know, as opposed to a known key with a bad value.
UNKNOWN_NAME_NOTE = re.compile(r": unknown (?:section|key|colour key) ")


class Report:
    """Collects errors and warnings and prints them, as GitHub annotations
    when running in an Action so they show on the pull request."""

    def __init__(self):
        self.errors = 0
        self.warnings = 0
        self.in_actions = os.environ.get("GITHUB_ACTIONS") == "true"

    def _emit(self, level, where, message):
        if self.in_actions:
            print(f"::{level} file={where}::{message}")
        else:
            print(f"{level.upper()} {where}: {message}")

    def error(self, where, message):
        self.errors += 1
        self._emit("error", where, message)

    def warning(self, where, message):
        self.warnings += 1
        self._emit("warning", where, message)


# --- RiftWii's own rules, through theme_check ------------------------------

def load_image_sizes(theme_check):
    """{name.png: (w, h)} straight from RiftWii's theme_images()."""
    output = subprocess.run([theme_check, "images"], check=True, capture_output=True, text=True).stdout
    sizes = {}
    for line in output.splitlines():
        name, width, height = line.split()
        sizes[name + ".png"] = (int(width), int(height))
    if not sizes:
        raise RuntimeError("theme_check listed no pictures")
    return sizes


def parse_ini_with_riftwii(theme_check, ini_path):
    """(name, author, notes) as RiftWii's parse_theme() sees the file."""
    result = subprocess.run([theme_check, "ini", str(ini_path)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"theme_check failed: {result.stderr.strip()}")
    name, author, notes = "", "", []
    for line in result.stdout.splitlines():
        field, _, value = line.partition("\t")
        if field == "name":
            name = value
        elif field == "author":
            author = value
        elif field == "note":
            notes.append(value)
    return name, author, notes


# --- File-format checks ----------------------------------------------------

def read_png(data):
    """(width, height, text) for a PNG, where text is its tEXt/iTXt words
    for the Nintendo check. Raises ValueError for anything RiftWii's decoder
    would refuse at the chunk level (src/art/pngdecode.cpp): wrong
    signature, IHDR not first, or a critical chunk with a bad CRC."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos = 8
    width = height = None
    texts = []
    seen_iend = False
    while pos + 12 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        crc_bytes = data[pos + 8 + length:pos + 12 + length]
        if len(body) != length or len(crc_bytes) != 4:
            raise ValueError(f"chunk {kind!r} runs past the end of the file")
        is_critical = not (kind[0] & 0x20)
        if is_critical and zlib.crc32(kind + body) != struct.unpack(">I", crc_bytes)[0]:
            raise ValueError(f"chunk {kind.decode('latin-1')} has a bad CRC")
        if width is None:
            if kind != b"IHDR" or length != 13:
                raise ValueError("first chunk is not IHDR")
            width, height = struct.unpack(">II", body[:8])
        if kind in (b"tEXt", b"iTXt"):
            texts.append(body.decode("latin-1"))
        pos += 12 + length
        if kind == b"IEND":
            seen_iend = True
            break
    if width is None or not seen_iend:
        raise ValueError("PNG is cut short (no IEND)")
    return width, height, " ".join(texts)


def read_ogg_vorbis(data):
    """(channels, rate, seconds, comments) for an Ogg Vorbis file. Raises
    ValueError for anything that is not Vorbis: RiftWii plays only Vorbis,
    and an Opus or a renamed MP3 would be skipped on the Wii."""
    if data[:4] != b"OggS":
        raise ValueError("not an Ogg file")
    # The first page holds only the identification header (Vorbis I spec,
    # 4.2.2): page header, segment table, then "\x01vorbis".
    segments = data[26]
    packet = data[27 + segments:]
    if packet[:7] != b"\x01vorbis":
        raise ValueError("Ogg file is not Vorbis (Opus, FLAC and others don't play on the Wii)")
    channels = packet[11]
    rate = struct.unpack("<I", packet[12:16])[0]
    # The last page's granule position is the total sample count.
    last_page = data.rfind(b"OggS", max(0, len(data) - 65536))
    if last_page < 0 or rate == 0:
        raise ValueError("Ogg file has no final page")
    total_samples = struct.unpack("<q", data[last_page + 6:last_page + 14])[0]
    seconds = total_samples / rate
    # The comment header (artist, title) follows on the next pages; a
    # search for the words is enough for a warning.
    comment_at = data.find(b"\x03vorbis")
    comments = data[comment_at:comment_at + 4096].decode("utf-8", "replace") if comment_at >= 0 else ""
    return channels, rate, seconds, comments


def check_wav(path, where, report):
    try:
        with wave.open(str(path), "rb") as sound:
            channels = sound.getnchannels()
            sample_width = sound.getsampwidth()
            rate = sound.getframerate()
            seconds = sound.getnframes() / rate if rate else 0
    except (wave.Error, EOFError) as problem:
        # RiftWii also takes AIFF and WAVE_FORMAT_EXTENSIBLE files, which
        # Python's wave module can't read; ask for plain PCM WAV instead.
        report.error(where, f"not a 16-bit PCM WAV this check can read ({problem})")
        return
    if sample_width != 2:
        report.error(where, f"must be 16-bit PCM, is {sample_width * 8}-bit")
    if channels not in (1, 2):
        report.error(where, f"must be mono or stereo, has {channels} channels")
    if rate not in SOUND_RATES:
        report.error(where, f"sample rate {rate} Hz is outside 4000-48000 Hz")
    if seconds > MAX_SOUND_SECONDS:
        report.error(where, f"{seconds:.1f} s long; RiftWii plays at most {MAX_SOUND_SECONDS:.0f} s")


def read_license(text):
    """{"license": id, "author": name} from the LICENSE file's header lines
    ("License: CC0-1.0", "Author: Someone"), the format CONTENT-RULES.md
    asks for."""
    fields = {}
    for line in text.splitlines():
        match = re.match(r"^\s*(License|Author)\s*:\s*(.*?)\s*$", line, re.IGNORECASE)
        if match and match.group(1).lower() not in fields:
            fields[match.group(1).lower()] = match.group(2)
    return fields


def load_approved_licenses(path):
    """{folder: license id} the maintainers approved one by one."""
    approved = {}
    if path and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                folder, license_id = line.split()
                approved[folder] = license_id
    return approved


def load_flagged_hashes(path):
    """{sha256: reason} of files known to be Nintendo's (or otherwise taken
    down), added by maintainers as reports come in."""
    flagged = {}
    if path and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                digest, _, reason = line.partition(" ")
                flagged[digest.lower()] = reason.strip() or "listed in flagged-sha256.txt"
    return flagged


# --- Names and paths -------------------------------------------------------

def name_problem(name):
    """Why a file name can't be in a theme, or None. The theme is unpacked
    on a FAT32 SD card by a Wii, so the rules are about what is safe there,
    not only on Linux."""
    # Checked before the hidden-file rule, so "..\evil.png" is reported as
    # what it is rather than as a dot file.
    if ".." in name or "/" in name or "\\" in name or ":" in name:
        return "name could climb out of the theme folder ('..', '/', '\\' or ':')"
    if name.startswith("."):
        return "hidden file"
    if any(ord(c) < 0x20 or ord(c) > 0x7E for c in name):
        return "name has control or non-ASCII characters"
    return None


def walk_theme(theme_dir, where, report):
    """Every regular file directly in the theme folder, as {name: Path}.
    Symlinks are never followed: a link could point at anything on the
    runner, and git can carry them."""
    files = {}
    theme_real = theme_dir.resolve()
    for entry in sorted(os.scandir(theme_dir), key=lambda e: e.name):
        entry_where = f"{where}/{entry.name}"
        problem = name_problem(entry.name)
        if problem:
            report.error(entry_where, problem)
            continue
        mode = entry.stat(follow_symlinks=False).st_mode
        if stat.S_ISLNK(mode):
            target = os.readlink(entry.path)
            resolved = (theme_dir / target).resolve()
            leaves = theme_real not in resolved.parents
            report.error(entry_where, f"symlinks are not allowed (points to {target!r}"
                                      f"{', outside the theme folder' if leaves else ''})")
            continue
        if stat.S_ISDIR(mode):
            report.error(entry_where, "themes are one flat folder; subfolders are not allowed")
            continue
        if not stat.S_ISREG(mode):
            report.error(entry_where, "not a regular file")
            continue
        files[entry.name] = Path(entry.path)
    return files


# --- One theme -------------------------------------------------------------

def validate_theme(theme_dir, image_sizes, theme_check, flagged, approved, report):
    folder = theme_dir.name
    where = f"themes/{folder}"
    errors_before = report.errors

    if not FOLDER_NAME.match(folder):
        report.error(where, "folder name must be 1-32 letters, digits, '_' or '-', starting with a letter or digit")

    files = walk_theme(theme_dir, where, report)
    allowed = FIXED_FILES | OPTIONAL_FILES | set(image_sizes)

    for name in sorted(set(files) - allowed):
        report.error(f"{where}/{name}", "not a file RiftWii uses; allowed are theme.ini, LICENSE, "
                                         "music.ogg, the four sound WAVs, preview.png and the pictures in docs/THEMES.md")
    for name in sorted(REQUIRED_FILES - set(files)):
        report.error(where, f"{name} is missing")

    total_bytes = sum(path.stat().st_size for path in files.values())
    if total_bytes > MAX_THEME_BYTES:
        report.error(where, f"theme is {total_bytes / 1048576:.1f} MiB; the limit is {MAX_THEME_BYTES // 1048576} MiB")

    for name, path in files.items():
        if name not in allowed:
            continue
        file_where = f"{where}/{name}"
        size = path.stat().st_size
        data = path.read_bytes()

        digest = hashlib.sha256(data).hexdigest()
        if digest in flagged:
            report.warning(file_where, f"matches a flagged file ({flagged[digest]}); a maintainer must check it")

        if name == PREVIEW_NAME:
            if size > MAX_PREVIEW_BYTES:
                report.error(file_where, f"{size} bytes; a preview may be at most {MAX_PREVIEW_BYTES} bytes")
            else:
                check_png(name, data, size, PREVIEW_SIZE, file_where, report)
        elif name in image_sizes:
            check_png(name, data, size, image_sizes[name], file_where, report)
        elif name == "music.ogg":
            check_music(data, size, file_where, report)
        elif name.endswith(".wav"):
            if size > MAX_SOUND_BYTES:
                report.error(file_where, f"{size} bytes; RiftWii skips sounds over {MAX_SOUND_BYTES} bytes")
            else:
                check_wav(path, file_where, report)

    if "theme.ini" in files:
        check_ini(files["theme.ini"], theme_check, folder, where, report)
    if "LICENSE" in files:
        check_license(files["LICENSE"], folder, approved, where, report)

    if report.errors == errors_before:
        print(f"OK {where} ({len(files)} files, {total_bytes} bytes)")


def check_png(name, data, size, expected, where, report):
    if size > MAX_PNG_BYTES:
        report.error(where, f"{size} bytes; RiftWii skips pictures over {MAX_PNG_BYTES} bytes")
        return
    try:
        width, height, text = read_png(data)
    except ValueError as problem:
        report.error(where, str(problem))
        return
    if (width, height) != expected and name == PREVIEW_NAME:
        report.error(where, f"is {width}x{height}; a preview is a {expected[0]}x{expected[1]} menu screenshot")
    elif (width, height) != expected:
        report.error(where, f"is {width}x{height}; RiftWii needs exactly {expected[0]}x{expected[1]} "
                            f"for {name} (a picture of any other size is skipped)")
    if SUSPICIOUS_WORDS.search(text):
        report.warning(where, f"PNG text mentions {SUSPICIOUS_WORDS.search(text).group(0)!r}; check where it came from")


def check_music(data, size, where, report):
    if size > MAX_MUSIC_BYTES:
        report.error(where, f"{size / 1048576:.1f} MiB; RiftWii skips music over 6 MiB")
        return
    try:
        channels, rate, seconds, comments = read_ogg_vorbis(data)
    except (ValueError, IndexError, struct.error) as problem:
        report.error(where, str(problem))
        return
    if channels not in (1, 2):
        report.error(where, f"must be mono or stereo, has {channels} channels")
    if rate not in MUSIC_RATES:
        report.error(where, f"sample rate {rate} Hz; RiftWii expects 44100 or 48000")
    if seconds > MAX_MUSIC_SECONDS:
        report.error(where, f"{seconds / 60:.1f} minutes long; the limit is {MAX_MUSIC_SECONDS // 60} minutes")
    if SUSPICIOUS_WORDS.search(comments):
        report.warning(where, f"Vorbis tags mention {SUSPICIOUS_WORDS.search(comments).group(0)!r}; "
                              "check the music is not ripped from a game")


def check_ini(path, theme_check, folder, where, report):
    file_where = f"{where}/theme.ini"
    if path.stat().st_size > MAX_INI_BYTES:
        report.error(file_where, f"over {MAX_INI_BYTES} bytes; RiftWii does not read it")
        return
    name, author, notes = parse_ini_with_riftwii(theme_check, path)
    # On the Wii a skipped line only falls back to a default. In a shared
    # list it is almost always a typo the author would want to know about,
    # so every note RiftWii would log fails the check here.
    for note in notes:
        # A name RiftWii doesn't know (a section or key) only warns: it may
        # be a setting from a newer RiftWii than RIFTWII_REF, and the Wii
        # ignores it harmlessly. A known key with a value RiftWii can't read
        # is always the author's mistake, so that fails.
        if UNKNOWN_NAME_NOTE.search(note):
            report.warning(file_where, f"RiftWii (at RIFTWII_REF) doesn't know this, so it is ignored: {note}")
        else:
            report.error(file_where, f"RiftWii would skip this: {note}")
    if not name:
        report.error(file_where, "[theme] name is missing; the theme list shows it")
    if not author:
        report.error(file_where, "[theme] author is missing")
    text = path.read_text(encoding="utf-8", errors="replace")
    if SUSPICIOUS_WORDS.search(text):
        report.warning(file_where, f"mentions {SUSPICIOUS_WORDS.search(text).group(0)!r}; check for Nintendo material")


def check_license(path, folder, approved, where, report):
    file_where = f"{where}/LICENSE"
    if path.stat().st_size > MAX_LICENSE_BYTES:
        report.error(file_where, f"over {MAX_LICENSE_BYTES} bytes")
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        report.error(file_where, "must be UTF-8 text")
        return
    fields = read_license(text)
    license_id = fields.get("license", "")
    if not license_id:
        report.error(file_where, "needs a 'License: <id>' line (CC0-1.0, CC-BY-4.0 or CC-BY-SA-4.0)")
    elif license_id not in ALLOWED_LICENSES and approved.get(folder) != license_id:
        report.error(file_where, f"license {license_id!r} is not CC0-1.0, CC-BY-4.0 or CC-BY-SA-4.0; "
                                 "other licenses need the maintainers' approval (scripts/approved-licenses.txt)")
    if not fields.get("author"):
        report.error(file_where, "needs an 'Author: <name>' line")
    if SUSPICIOUS_WORDS.search(text):
        report.warning(file_where, f"mentions {SUSPICIOUS_WORDS.search(text).group(0)!r}; check for Nintendo material")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--theme-check", required=True, help="theme_check built from RiftWii's theme.cpp")
    parser.add_argument("--flagged", type=Path, help="flagged-sha256.txt")
    parser.add_argument("--approved", type=Path, help="approved-licenses.txt")
    parser.add_argument("--all", type=Path, help="check every folder in this themes directory")
    parser.add_argument("themes", nargs="*", type=Path)
    args = parser.parse_args()

    theme_dirs = list(args.themes)
    report = Report()
    if args.all:
        for entry in sorted(args.all.iterdir()):
            # themes/README.md explains the folder; it is not a theme.
            if entry.name == "README.md" and entry.is_file() and not entry.is_symlink():
                continue
            if entry.is_dir() and not entry.is_symlink():
                theme_dirs.append(entry)
            else:
                report.error(f"themes/{entry.name}", "only theme folders belong in themes/")
    if not theme_dirs and report.errors == 0:
        # An empty themes/ is fine with --all (the repository starts that
        # way, and a pull request may only change the docs).
        if args.all:
            print("no themes yet: nothing to check")
            return 0
        parser.error("no themes to check")

    image_sizes = load_image_sizes(args.theme_check)
    flagged = load_flagged_hashes(args.flagged)
    approved = load_approved_licenses(args.approved)
    for theme_dir in theme_dirs:
        validate_theme(theme_dir, image_sizes, args.theme_check, flagged, approved, report)

    print(f"{report.errors} error(s), {report.warnings} warning(s)")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
