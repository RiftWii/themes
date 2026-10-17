#!/bin/sh
# SPDX-FileCopyrightText: 2026 RiftWii contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Builds scripts/theme_check.cpp against a RiftWii checkout:
#
#   scripts/build_theme_check.sh <riftwii checkout> <output binary>
#
# Only two RiftWii files are needed: src/art/theme.cpp depends on nothing
# but its header and the C++ standard library, so the Actions can use a
# sparse checkout and build in a second instead of the whole host library.
set -eu

if [ "$#" -ne 2 ]; then
    echo "usage: $0 <riftwii checkout> <output binary>" >&2
    exit 2
fi

riftwii="$1"
output="$2"
here="$(cd "$(dirname "$0")" && pwd)"

${CXX:-c++} -std=c++17 -O1 -Wall -Wextra \
    -I "$riftwii/include" \
    "$here/theme_check.cpp" "$riftwii/src/art/theme.cpp" \
    -o "$output"
