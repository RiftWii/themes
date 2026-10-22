// SPDX-FileCopyrightText: 2026 RiftWii contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
// A tiny host program around RiftWii's own theme code (src/art/theme.cpp),
// so the themes repository accepts exactly what the Wii accepts instead of
// keeping a second copy of the rules in Python that could drift.
//
//   theme_check images         one line per picture a theme may replace:
//                              "<name> <width> <height>"
//   theme_check ini <path>     parses theme.ini and prints
//                              "name\t<name>", "author\t<author>" and one
//                              "note\t<text>" per line RiftWii would skip,
//                              then the settings RiftWii ended up with, for
//                              scripts/mock_preview.py: "corners\t<number>",
//                              "stripes\t0|1", "gloss\t0|1", "bar\tdip|bump"
//                              and one "color\t<key>\t#RRGGBBAA" per colour
//
// It always exits 0 after a successful read: RiftWii never refuses a
// theme.ini, it only skips lines, so deciding that a note is a failure is
// the validator's policy (scripts/validate_theme.py), not this program's.
// Exit 2 means it could not run at all (bad arguments, unreadable file).
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

#include "riftwii/theme.hpp"

namespace {

int print_images() {
    for (const riftwii::ThemeImage& image : riftwii::theme_images()) {
        std::cout << image.name << ' ' << image.w << ' ' << image.h << '\n';
    }
    return 0;
}

// Tabs and newlines inside a value would break the line format, and
// RiftWii's parser trims spaces and tabs but keeps any other byte, so
// escape them rather than drop them.
std::string escape_field(const std::string& value) {
    std::string out;
    for (char c : value) {
        if (c == '\t') {
            out += "\\t";
        } else if (c == '\n') {
            out += "\\n";
        } else if (c == '\\') {
            out += "\\\\";
        } else {
            out += c;
        }
    }
    return out;
}

int print_ini(const char* path) {
    // Binary mode: the Wii reads the raw bytes, BOM and CRLF included, and
    // parse_theme() handles both itself.
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        std::cerr << "theme_check: cannot open " << path << '\n';
        return 2;
    }
    const std::string text((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());

    std::vector<std::string> notes;
    const riftwii::Theme theme = riftwii::parse_theme(text, notes);

    std::cout << "name\t" << escape_field(theme.name) << '\n';
    std::cout << "author\t" << escape_field(theme.author) << '\n';
    for (const std::string& note : notes) {
        std::cout << "note\t" << escape_field(note) << '\n';
    }

    // The settings after RiftWii's own parsing, with its defaults filled
    // in, so the mock preview draws from the values the Wii would use.
    std::cout << "corners\t" << theme.corners << '\n';
    std::cout << "stripes\t" << (theme.stripes ? 1 : 0) << '\n';
    std::cout << "gloss\t" << (theme.gloss ? 1 : 0) << '\n';
    std::cout << "bar\t" << (theme.bar_bump ? "bump" : "dip") << '\n';
    for (const riftwii::ThemeColorKey& entry : riftwii::theme_color_keys()) {
        std::cout << "color\t" << entry.key << '\t' << riftwii::format_theme_color(theme.colors.*(entry.field)) << '\n';
    }
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    const std::string mode = (argc >= 2) ? argv[1] : "";
    if (mode == "images" && argc == 2) {
        return print_images();
    }
    if (mode == "ini" && argc == 3) {
        return print_ini(argv[2]);
    }
    std::cerr << "usage: theme_check images\n"
                 "       theme_check ini <theme.ini>\n";
    return 2;
}
