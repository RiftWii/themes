#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RiftWii contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Draws a mock of RiftWii's Home with a theme on it, as a 640x480 PNG.

    mock_preview.py --theme-check BIN --out DIR THEME_DIR...

Every theme's preview is drawn, so all themes look alike and are easy to
compare. A gradient background says nothing about how a menu looks. This draws
the theme's own pictures and colors into RiftWii's Home layout: the grid of
tiles (one focused), the bottom bar with its clock, the round buttons and
the page label. It is a mock, not a screenshot: tile contents are
placeholders (no game names or covers), and anything RiftWii animates or
draws with its own code is approximated (see "Not matched" at the end of
the layout block).

Needs Pillow (pinned in scripts/requirements-preview.txt). The theme's
colors and shape come from theme_check, which is RiftWii's own theme.cpp,
so defaults and parsing are the Wii's, not a copy here.

Every file in a theme is untrusted. Pictures are opened as PNG only, their
file size and header size are checked before any pixel is decoded, and
Pillow's decompression-bomb limit is set far below its default and treated
as an error. Nothing from a theme is imported or run, and the only program
started is theme_check, with fixed arguments.
"""

import argparse
import io
import math
import subprocess
import sys
import warnings
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_theme import MAX_PNG_BYTES, load_image_sizes  # noqa: E402

# --- Limits ----------------------------------------------------------------
#
# The biggest picture RiftWii accepts is 856x480 (background_wide), so two
# million pixels is generous. Pillow's own default is 89 million.
Image.MAX_IMAGE_PIXELS = 2_000_000
# A picture over the limit only warns, and is refused outright at twice it;
# load_picture() turns the warning into an error as well.

# --- RiftWii's Home, in screen pixels --------------------------------------
#
# Every number here is copied from RiftWii (KakarottoCake/Riftwii, main) so
# this file can be updated when the menu changes. All are for a 4:3 menu
# (640x480), the names view with normal spacing (grid_spacing = normal).
#
# wii/menu/gui_gamegrid.cpp, GuiGameGrid::Geo(), "names": 4 columns of
# 12-tile pages (kPerPage = 12, so 3 rows), each tile 120x84, the first at
# x 61, y 30, 13 apart across and 12 down.
GRID_COLUMNS, GRID_ROWS = 4, 3
TILE_W, TILE_H = 120, 84
GRID_LEFT, GRID_TOP = 61, 30
GRID_GAP_X, GRID_GAP_Y = 13, 12
# The tile pictures (docs/THEMES.md: tile, tile_over, tile_empty are 140x100,
# the 124x84 card plus a 7 px margin for shadow and glow, rounded up to GX's
# 4x4 blocks) are drawn centered on the tile (DrawTilePicture).
TILE_PICTURE = (140, 100)
TILE_CARD = (124, 84)       # src/art/skinpaint.cpp, Painter::Tile(124, 84, 7, 14, ...)
TILE_MARGIN = 7
TILE_RADIUS = 14            # multiplied by the theme's [shape] corners
# wii/menu/gui_gamegrid.cpp, DrawNameTile(): the text starts kTextLeft (11)
# in, the first line 9 down and the second 27; the game's color runs as a
# 3 px strip 7 px up from the bottom, inset 12 px each side; the source
# badge (DISC/USB/SD) and the ID sit on a line 26 up from the bottom.
TEXT_LEFT = 11
TITLE_LINE_Y = (9, 27)
HUE_STRIP_INSET, HUE_STRIP_FROM_BOTTOM, HUE_STRIP_H = 12, 7, 3
BADGE_LINE_FROM_BOTTOM, BADGE_H = 26, 15
# The tile that is lit (tile_over): second row, second column.
FOCUSED_TILE = 5
# How many of the page's 12 tiles hold a game; the rest are empty places
# (tile_empty), as a card with a few games shows them.
TILES_WITH_GAMES = 9

# wii/menu/rift_menu.cpp, class HomeBar: bar.png (640x124) is drawn with its
# top at 356 - kLift (18) = 338; below it the screen is filled with the
# picture's last row. Its shape when it is not a picture: src/art/
# skinpaint.cpp, Painter::Bar() (dip) and BumpBar() (bump).
BAR_TOP = 356 - 18
BAR_SIZE = (640, 124)
# Painter::Bar(): the line sits at y 11 at the sides and 62 in the dip,
# which is 58% of the width, sloping in over 30% of it each side.
BAR_DIP_WIDTH = 0.58
BAR_SIDE_Y, BAR_DIP_DEPTH, BAR_SLOPE = 11, 51, 0.3
# Painter::BumpBar(): the line at y 46 at the sides, 14 at the top of a bump
# 288 wide, in the middle.
BUMP_SIDE_Y, BUMP_RISE, BUMP_WIDTH = 46, 32, 288

# wii/menu/rift_menu.cpp, MenuHome (Home's widgets). With a bar that dips:
#   the clock: seven-segment figures, 40 high, centered on x 320, top y 351
#   (class LcdClock; skinpaint.cpp ClockDigits has 28x44 cells);
#   the date: 22 px, centered, y 407, in ink_soft;
#   the view's name: 14 px, left at x 36, y 354, in accent;
#   the page: 14 px, right edge at x 604, y 354, in ink_dim.
# With a bar that bumps: the clock above the bump (34 px text, centered,
# y 296), the date in it (18 px, y 359), the page at (40, 300) 15 px and the
# view at (40, 324) 16 px.
CLOCK_TOP, CLOCK_H = 351, 40
LCD_CELL = (28, 44)
DATE_Y_DIP, DATE_SIZE_DIP = 407, 22
VIEW_POS_DIP, PAGE_RIGHT_DIP, LABEL_Y_DIP, LABEL_SIZE_DIP = 36, 604, 354, 14
BUMP_CLOCK_Y, BUMP_CLOCK_SIZE = 296, 34
BUMP_DATE_Y, BUMP_DATE_SIZE = 359, 18
BUMP_PAGE_POS, BUMP_PAGE_SIZE = (40, 300), 15
BUMP_VIEW_POS, BUMP_VIEW_SIZE = (40, 324), 16
# The round buttons (round_button.png, 80x80): filter at (34, 376), settings
# at (530, 376); the search button is half size at (568, 24). Their icons
# (icon_drives, icon_gear, icon_search, 28x28) are centered on them.
ROUND_BUTTONS = ((34, 376, 80, "icon_drives"), (530, 376, 80, "icon_gear"), (568, 24, 40, "icon_search"))
# The next-page arrow (arrow_right.png, 48x48) at x 570, level with the
# middle of the grid: GuiGameGrid::ArrowX() / ArrowY().
ARROW_RIGHT_X = 570
# Settings: src/art/skin* "backdrop stripes": 2 px lines every 4 px from y 2
# (SkinDrawBackdrop in wii/menu/skin.cpp).
STRIPE_FIRST, STRIPE_STEP, STRIPE_H = 2, 4, 2

# What this does not match (a mock, drawn once, from the files and not the
# Wii's GX renderer):
#  - the tile text, badges and the game's color strip are placeholders;
#  - the clock's digits are drawn as plain seven-segment lines, not
#    skinpaint.cpp's shaded ClockDigits picture;
#  - the painted tile, round button, arrow and bar are close copies of
#    skinpaint.cpp's shapes (radius, border widths, shine), not pixel-exact;
#  - a theme with a `shelf` or `background_shelf` look is drawn in the names
#    view, which is Home's default, and the pointer, toasts and the
#    two-way hover names are left out.

PREVIEW_SIZE = (640, 480)
SUPERSAMPLE = 4  # shapes are drawn 4x larger and scaled down, for smooth edges
FONT_SIZES = (11, 14, 15, 16, 18, 22, 34)
PLACEHOLDER_HUES = ((72, 112, 190), (190, 80, 80), (80, 160, 100), (200, 160, 50),
                    (130, 90, 180), (60, 150, 170), (190, 110, 60), (110, 130, 70), (150, 80, 130))


# --- Reading the theme -------------------------------------------------------

def parse_color(text):
    """(r, g, b, a) from "#RRGGBB" or "#RRGGBBAA" (theme_check's format)."""
    digits = text.lstrip("#")
    if len(digits) == 6:
        digits += "FF"
    return tuple(int(digits[i:i + 2], 16) for i in range(0, 8, 2))


class ThemeLook:
    """What RiftWii's parse_theme() made of a theme.ini."""

    def __init__(self, corners, stripes, gloss, bump, colors):
        self.corners = corners
        self.stripes = stripes
        self.gloss = gloss
        self.bump = bump
        self.colors = colors


def read_theme_look(theme_check, ini_path):
    """Runs `theme_check ini` and reads the settings it prints after the
    name, author and notes. Raises RuntimeError when it can't run, or when
    it prints no colors (a theme_check from before this script existed)."""
    result = subprocess.run([theme_check, "ini", str(ini_path)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", check=False)
    if result.returncode != 0:
        raise RuntimeError(f"theme_check failed: {result.stderr.strip()}")
    corners, stripes, gloss, bump, colors = 1.0, True, False, False, {}
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if fields[0] == "corners" and len(fields) == 2:
            corners = max(0.0, min(2.0, float(fields[1])))
        elif fields[0] == "stripes" and len(fields) == 2:
            stripes = fields[1] == "1"
        elif fields[0] == "gloss" and len(fields) == 2:
            gloss = fields[1] == "1"
        elif fields[0] == "bar" and len(fields) == 2:
            bump = fields[1] == "bump"
        elif fields[0] == "color" and len(fields) == 3:
            colors[fields[1]] = parse_color(fields[2])
    if "backdrop" not in colors:
        raise RuntimeError("theme_check printed no colors; rebuild it from scripts/theme_check.cpp")
    return ThemeLook(corners, stripes, gloss, bump, colors)


def load_picture(theme_dir, name, size):
    """A theme's <name>.png as RGBA, or None when it is missing or not
    usable. The size is checked from the header before any pixel is decoded,
    like RiftWii (a picture of another size is skipped), and a PNG that
    Pillow won't decode safely is treated as missing, not as a failure: the
    mock then paints that part itself."""
    path = theme_dir / f"{name}.png"
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_PNG_BYTES:
            return None
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            picture = Image.open(io.BytesIO(path.read_bytes()), formats=["PNG"])
            if picture.size != tuple(size):
                return None
            picture.load()
            return picture.convert("RGBA")
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return None


# --- Drawing helpers -----------------------------------------------------------

def font(size):
    """Pillow's bundled font (Aileron, CC0), at `size`. It ships inside
    Pillow, so nothing is committed here and no Nintendo font is involved.
    Falls back to Pillow's fixed-size bitmap font if FreeType is missing."""
    try:
        return ImageFont.load_default(size)
    except (TypeError, OSError):
        return ImageFont.load_default()


def over(canvas, layer, x, y):
    """`layer` (RGBA) laid over the opaque canvas at x, y, cut to the canvas."""
    canvas.paste(layer, (int(x), int(y)), layer)


def with_alpha(color, factor):
    return color[0], color[1], color[2], int(color[3] * factor)


def supersampled(width, height):
    """A transparent layer 4x the size to draw on, and its drawing context."""
    big = Image.new("RGBA", (width * SUPERSAMPLE, height * SUPERSAMPLE), (0, 0, 0, 0))
    return big, ImageDraw.Draw(big)


def finished(big, width, height):
    return big.resize((width, height), Image.LANCZOS)


def rounded_box(draw, left, top, box_w, box_h, radius, fill=None, outline=None, outline_w=0):
    """A rounded rectangle in layout pixels, on a supersampled layer."""
    k = SUPERSAMPLE
    box = (left * k, top * k, (left + box_w) * k - 1, (top + box_h) * k - 1)
    draw.rounded_rectangle(box, radius=max(0, radius * k), fill=fill, outline=outline, width=int(outline_w * k))


def soft_shadow(width, height, left, top, box_w, box_h, radius, color, blur, drop):
    """A blurred rounded shape, `drop` lower than the box it shadows."""
    big, draw = supersampled(width, height)
    rounded_box(draw, left, top + drop, box_w, box_h, radius, fill=color)
    return finished(big.filter(ImageFilter.GaussianBlur(blur * SUPERSAMPLE / 2)), width, height)


def painted_card(colors, look, card_w, card_h, margin, radius, lit):
    """A card as skinpaint.cpp's Painter::Tile() paints it: shadow, the
    card color, a shine when the theme has `gloss`, a fine edge (lit: the
    accent's 3 px border over a glow). Returns an RGBA layer of the card
    plus its margin."""
    width, height = card_w + 2 * margin, card_h + 2 * margin
    radius = radius * look.corners
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if lit:
        glow = soft_shadow(width, height, margin - 1, margin - 1, card_w + 2, card_h + 2, radius + 1,
                           colors["glow"], margin, 0)
        layer = Image.alpha_composite(layer, glow)
    shadow = soft_shadow(width, height, margin, margin, card_w, card_h, radius, colors["shadow"], 3, 2)
    layer = Image.alpha_composite(layer, shadow)
    big, draw = supersampled(width, height)
    rounded_box(draw, margin, margin, card_w, card_h, radius, fill=colors["card"])
    if look.gloss:
        # The top half: white fading from 120/255 to 30/255 down the card.
        top = margin * SUPERSAMPLE
        half = (card_h // 2) * SUPERSAMPLE
        shine = Image.new("RGBA", big.size, (0, 0, 0, 0))
        shine_draw = ImageDraw.Draw(shine)
        for row in range(half):
            alpha = int(120 + (30 - 120) * row / max(1, half - 1))
            shine_draw.line([(0, top + row), (big.width, top + row)], fill=(255, 255, 255, alpha))
        # Only where the card is: the shine follows its rounded corners.
        mask = Image.new("L", big.size, 0)
        rounded_box(ImageDraw.Draw(mask), margin, margin, card_w, card_h, radius, fill=255)
        shine.putalpha(ImageChops.multiply(shine.getchannel("A"), mask))
        big = Image.alpha_composite(big, shine)
        draw = ImageDraw.Draw(big)
    border_color, border_w = (colors["accent"], 3) if lit else (colors["card_edge"], 2)
    rounded_box(draw, margin, margin, card_w, card_h, radius, outline=border_color, outline_w=border_w)
    return Image.alpha_composite(layer, finished(big, width, height))


def painted_empty_tile(colors, look, card_w, card_h, margin, radius):
    """An empty place, as Painter::TileEmpty(): the backdrop's color a shade
    darker with fine lines across it and a fine edge."""
    width, height = card_w + 2 * margin, card_h + 2 * margin
    radius = radius * look.corners
    backdrop = colors["backdrop"]
    shaded = tuple(min(255, int(channel * 0.97)) for channel in backdrop[:3]) + (255,)
    big, draw = supersampled(width, height)
    rounded_box(draw, margin, margin, card_w, card_h, radius, fill=shaded)
    line = tuple(int(channel * 0.90) for channel in backdrop[:3]) + (70,)
    for row in range(margin + 3, margin + card_h - 3, 3):
        draw.line([((margin + 3) * SUPERSAMPLE, row * SUPERSAMPLE),
                   ((margin + card_w - 3) * SUPERSAMPLE, row * SUPERSAMPLE)], fill=line, width=SUPERSAMPLE)
    edge = with_alpha(colors["card_edge"], 200 / 255)
    rounded_box(draw, margin, margin, card_w, card_h, radius, outline=edge, outline_w=1.5)
    return finished(big, width, height)


def painted_round_button(colors, size):
    """Painter::Round(): a card-colored disc with the rim's edge."""
    margin = 3
    big, draw = supersampled(size, size)
    k = size / 80.0
    shadow = soft_shadow(size, size, margin * k, margin * k, 74 * k, 74 * k, 37 * k, colors["shadow"], 3 * k, 1)
    k4 = SUPERSAMPLE
    draw.ellipse((margin * k * k4, margin * k * k4, (margin + 74) * k * k4, (margin + 74) * k * k4),
                 fill=colors["card"], outline=colors["card_edge_strong"], width=int(2 * k4))
    return Image.alpha_composite(shadow, finished(big, size, size))


def seven_segment_clock(canvas, text, center_x, top, height, color):
    """Digits and a colon in seven-segment strokes, 28x44 cells scaled to
    `height` (skinpaint.cpp ClockDigits' segments, Painter::ClockDigits)."""
    scale = height / LCD_CELL[1]
    cell_w = LCD_CELL[0] * scale
    segments = {
        "a": (8, 4, 20, 4), "b": (24, 8, 24, 18), "c": (24, 26, 24, 36), "d": (8, 40, 20, 40),
        "e": (4, 26, 4, 36), "f": (4, 8, 4, 18), "g": (8, 22, 20, 22),
    }
    lit = {"0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg", "5": "acdfg",
           "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg"}
    width = int(cell_w * len(text)) + 8
    big, draw = supersampled(width, int(height) + 8)
    k = SUPERSAMPLE * scale
    for index, character in enumerate(text):
        origin = index * LCD_CELL[0]
        if character == ":":
            for dot_y in (14, 30):
                cx, cy = (origin + 14) * k, (dot_y + 4) * k
                draw.ellipse((cx - 2.5 * k, cy - 2.5 * k, cx + 2.5 * k, cy + 2.5 * k), fill=color)
            continue
        for name in lit[character]:
            x0, y0, x1, y1 = segments[name]
            draw.line([((origin + x0) * k, (y0 + 4) * k), ((origin + x1) * k, (y1 + 4) * k)],
                      fill=color, width=int(4.5 * k))
            for end_x, end_y in ((x0, y0), (x1, y1)):
                cx, cy = (origin + end_x) * k, (end_y + 4) * k
                draw.ellipse((cx - 2.25 * k, cy - 2.25 * k, cx + 2.25 * k, cy + 2.25 * k), fill=color)
    layer = finished(big, width, int(height) + 8)
    over(canvas, layer, center_x - width / 2, top - 4)


def text_at(canvas, position, text, size, color, anchor="la"):
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(position, text, font=font(size), fill=color, anchor=anchor)
    canvas.alpha_composite(layer)


def bar_profile(look, width):
    """The bar's top edge, y for each x, as Painter::Bar()/BumpBar()."""
    top = []
    for x in range(width):
        if look.bump:
            t = (x + 0.5 - (width / 2.0 - BUMP_WIDTH / 2.0)) / BUMP_WIDTH
            rise = (1.0 - math.cos(t * 2.0 * math.pi)) * 0.5 if 0.0 < t < 1.0 else 0.0
            top.append(BUMP_SIDE_Y - BUMP_RISE * rise)
        else:
            dip = width * BAR_DIP_WIDTH
            t = (x + 0.5 - (width / 2.0 - dip / 2.0)) / dip

            def ease(v):
                v = min(1.0, max(0.0, v))
                return v * v * (3 - 2 * v)
            depth = min(ease(t / BAR_SLOPE), ease((1.0 - t) / BAR_SLOPE)) if 0.0 < t < 1.0 else 0.0
            top.append(BAR_SIDE_Y + BAR_DIP_DEPTH * depth)
    return top


def painted_bar(colors, look):
    """The bar as Painter::Bar() paints it: a shade over what is above,
    the body shaded down from the line, the accent's line with a light edge
    under it."""
    width, height = BAR_SIZE
    top = bar_profile(look, width)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pixels = layer.load()
    bar = colors["bar"]
    for x in range(width):
        for y in range(height):
            if y < top[x] - 4 - 6:
                continue
            if y < top[x] - 4:  # the soft shade over what is above the line
                pixels[x, y] = (0, 0, 0, int(22 * (1 - (top[x] - 4 - y) / 6.0)))
            elif y >= top[x]:
                shade = 1.0 - 0.10 * (y / (height - 1.0))
                row = [int(bar[0] * shade), int(bar[1] * shade), int(bar[2] * shade), 255]
                if look.stripes and not look.bump and (y & 3) >= 2:
                    row = [int(channel * 0.97) for channel in row[:3]] + [255]
                pixels[x, y] = tuple(row)
    big, draw = supersampled(width, height)
    k = SUPERSAMPLE
    draw.line([(x * k + k / 2, (top[x] + 3) * k) for x in range(width)], fill=(255, 255, 255, 150), width=2 * k)
    draw.line([(x * k + k / 2, top[x] * k) for x in range(width)], fill=colors["accent"], width=int(3.5 * k))
    return Image.alpha_composite(layer, finished(big, width, height))


# --- The picture ---------------------------------------------------------------

def render_mock(theme_dir, theme_check, image_sizes=None):
    """RiftWii's Home with the theme on, as a 640x480 RGB Image."""
    theme_dir = Path(theme_dir)
    if image_sizes is None:
        image_sizes = load_image_sizes(theme_check)
    look = read_theme_look(theme_check, theme_dir / "theme.ini")
    colors = look.colors

    def picture(name):
        return load_picture(theme_dir, name, image_sizes[name + ".png"]) if name + ".png" in image_sizes else None

    canvas = Image.new("RGBA", PREVIEW_SIZE, colors["backdrop"][:3] + (255,))

    # The backdrop: background.png wins over the color and the stripes.
    background = picture("background")
    if background is not None:
        canvas.paste(background, (0, 0))
    elif look.stripes:
        draw = ImageDraw.Draw(canvas)
        for y in range(STRIPE_FIRST, PREVIEW_SIZE[1], STRIPE_STEP):
            draw.rectangle((0, y, PREVIEW_SIZE[0], y + STRIPE_H - 1), fill=colors["backdrop_stripe"])
        canvas = Image.alpha_composite(Image.new("RGBA", canvas.size, (0, 0, 0, 0)), canvas)

    # The grid of tiles: a page of 12, most with a game, the rest empty.
    tile_picture, tile_over = picture("tile"), picture("tile_over")
    empty_picture = picture("tile_empty")
    painted = {}

    def tile_layer(kind):
        existing = {"tile": tile_picture, "over": tile_over, "empty": empty_picture}[kind]
        if existing is not None:
            return existing
        if kind not in painted:
            if kind == "empty":
                painted[kind] = painted_empty_tile(colors, look, TILE_CARD[0], TILE_CARD[1], TILE_MARGIN, TILE_RADIUS)
            else:
                painted[kind] = painted_card(colors, look, TILE_CARD[0], TILE_CARD[1], TILE_MARGIN, TILE_RADIUS,
                                             kind == "over")
        return painted[kind]

    for index in range(GRID_COLUMNS * GRID_ROWS):
        column, row = index % GRID_COLUMNS, index // GRID_COLUMNS
        x = GRID_LEFT + column * (TILE_W + GRID_GAP_X)
        y = GRID_TOP + row * (TILE_H + GRID_GAP_Y)
        has_game = index < TILES_WITH_GAMES
        kind = "empty" if not has_game else "over" if index == FOCUSED_TILE else "tile"
        layer = tile_layer(kind)
        over(canvas, layer, x + TILE_W / 2 - layer.width / 2, y + TILE_H / 2 - layer.height / 2)
        if has_game:
            draw_placeholder_game(canvas, colors, x, y, index)

    # The bar and everything on it.
    bar_picture = picture("bar")
    bar_layer = bar_picture if bar_picture is not None else painted_bar(colors, look)
    bar_x = (PREVIEW_SIZE[0] - bar_layer.width) // 2
    over(canvas, bar_layer, bar_x, BAR_TOP)
    # Below the picture, to the screen's bottom: its last row repeated.
    below = BAR_TOP + bar_layer.height
    if below < PREVIEW_SIZE[1]:
        last_row = bar_layer.crop((0, bar_layer.height - 1, bar_layer.width, bar_layer.height))
        over(canvas, last_row.resize((bar_layer.width, PREVIEW_SIZE[1] - below)), bar_x, below)

    for x, y, size, icon_name in ROUND_BUTTONS:
        button = picture("round_button") if size == 80 else None
        if button is None:
            button = painted_round_button(colors, size)
        elif size != 80:
            button = button.resize((size, size), Image.LANCZOS)
        over(canvas, button, x, y)
        icon = picture(icon_name)
        if icon is not None:
            over(canvas, icon, x + size / 2 - icon.width / 2, y + size / 2 - icon.height / 2)
        else:
            draw_placeholder_icon(canvas, colors, x + size / 2, y + size / 2, size)

    draw_next_page_arrow(canvas, colors, picture("arrow_right"))
    draw_bar_texts(canvas, colors, look)
    return canvas.convert("RGB")


def draw_placeholder_game(canvas, colors, x, y, index):
    """What a game's tile holds, without any real name or cover: two bars
    where its title goes, its ID, a source badge and the game's color."""
    ink = colors["ink"]
    line_alpha = (150, 90)
    for row, line_y in enumerate(TITLE_LINE_Y):
        width = (TILE_W - 2 * TEXT_LEFT - 20) if row == 0 else (TILE_W - 2 * TEXT_LEFT) // 2
        layer = Image.new("RGBA", (width, 8), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle((0, 0, width - 1, 7), radius=3, fill=with_alpha(ink, line_alpha[row] / 255))
        over(canvas, layer, x + TEXT_LEFT, y + line_y + 4)
    base_y = y + TILE_H - BADGE_LINE_FROM_BOTTOM
    badge_w = 24
    badge = Image.new("RGBA", (badge_w, BADGE_H), (0, 0, 0, 0))
    badge_draw = ImageDraw.Draw(badge)
    badge_draw.rectangle((0, 0, badge_w - 1, BADGE_H - 1), fill=colors["badge"])
    badge_draw.text((badge_w / 2, BADGE_H / 2), "SD", font=font(11), fill=colors["ink_dim"], anchor="mm")
    over(canvas, badge, x + TILE_W - TEXT_LEFT - badge_w, base_y - 1)
    id_bar = Image.new("RGBA", (36, 5), (0, 0, 0, 0))
    ImageDraw.Draw(id_bar).rounded_rectangle((0, 0, 35, 4), radius=2, fill=with_alpha(colors["ink_dim"], 0.6))
    over(canvas, id_bar, x + TEXT_LEFT, base_y + 4)
    hue = PLACEHOLDER_HUES[index % len(PLACEHOLDER_HUES)]
    strip = Image.new("RGBA", (TILE_W - 2 * HUE_STRIP_INSET, HUE_STRIP_H), hue + (255,))
    over(canvas, strip, x + HUE_STRIP_INSET, y + TILE_H - HUE_STRIP_FROM_BOTTOM)


def draw_placeholder_icon(canvas, colors, center_x, center_y, button_size):
    """A button's icon when the theme has none of its own: a plain dot
    ring in the glyph color, standing for the drive/gear/magnifier."""
    radius = 7 if button_size == 80 else 4
    layer = Image.new("RGBA", (radius * 8, radius * 8), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((radius * 2, radius * 2, radius * 6, radius * 6), outline=colors["glyph"], width=2)
    over(canvas, layer, center_x - radius * 4, center_y - radius * 4)


def draw_next_page_arrow(canvas, colors, arrow):
    grid_height = GRID_ROWS * TILE_H + (GRID_ROWS - 1) * GRID_GAP_Y
    y = GRID_TOP + grid_height // 2 - 22
    if arrow is not None:
        over(canvas, arrow, ARROW_RIGHT_X, y)
        return
    big, draw = supersampled(44, 44)
    k = SUPERSAMPLE
    draw.line([(16 * k, 10 * k), (28 * k, 22 * k), (16 * k, 34 * k)], fill=colors["glyph"], width=5 * k, joint="curve")
    over(canvas, finished(big, 44, 44), ARROW_RIGHT_X + 2, y)


def draw_bar_texts(canvas, colors, look):
    """The clock, date, the view's name and the page label in the theme's
    ink colors. The strings are fixed, so a theme's preview doesn't change
    from one publish to the next."""
    page, view, date = "Page 1 of 3", "All games", "Mon 1/5"
    if look.bump:
        text_at(canvas, (320, BUMP_CLOCK_Y), "12:34", BUMP_CLOCK_SIZE, colors["clock"], "ma")
        text_at(canvas, (320, BUMP_DATE_Y), date, BUMP_DATE_SIZE, colors["ink_soft"], "ma")
        text_at(canvas, BUMP_PAGE_POS, page, BUMP_PAGE_SIZE, colors["ink_dim"], "la")
        text_at(canvas, BUMP_VIEW_POS, view, BUMP_VIEW_SIZE, colors["accent"], "la")
        return
    seven_segment_clock(canvas, "12:34", 320, CLOCK_TOP, CLOCK_H, colors["clock"])
    text_at(canvas, (320, DATE_Y_DIP), date, DATE_SIZE_DIP, colors["ink_soft"], "ma")
    text_at(canvas, (VIEW_POS_DIP, LABEL_Y_DIP), view, LABEL_SIZE_DIP, colors["accent"], "la")
    text_at(canvas, (PAGE_RIGHT_DIP, LABEL_Y_DIP), page, LABEL_SIZE_DIP, colors["ink_dim"], "ra")


def write_mock(theme_dir, theme_check, out_path, image_sizes=None):
    """Draws the theme's mock and saves it as a PNG at out_path."""
    mock = render_mock(theme_dir, theme_check, image_sizes)
    mock.save(out_path, format="PNG", optimize=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--theme-check", required=True)
    parser.add_argument("--out", type=Path, required=True, help="folder to write <theme>.png files into")
    parser.add_argument("themes", nargs="+", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    image_sizes = load_image_sizes(args.theme_check)
    for theme_dir in args.themes:
        out_path = args.out / f"{theme_dir.name}.png"
        write_mock(theme_dir, args.theme_check, out_path, image_sizes)
        print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
