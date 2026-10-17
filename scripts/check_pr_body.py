#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 RiftWii contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fails unless every tick box in the pull request template is ticked.

    check_pr_body.py --template .github/PULL_REQUEST_TEMPLATE.md --event "$GITHUB_EVENT_PATH"
    check_pr_body.py --template .github/PULL_REQUEST_TEMPLATE.md --body-file body.md

The boxes are read from the template itself (from the base branch, so a
pull request can't edit them away), which keeps the check and the template
from drifting apart: add a "- [ ] ..." line to the template and it is
required. A box counts when its line appears in the body, ticked ("- [x]"),
with the same words; spaces and case don't matter.
"""

import argparse
import json
import re
import sys
from pathlib import Path

BOX = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.+?)\s*$")


def normalize(text):
    return " ".join(text.split()).lower()


def boxes(markdown):
    """{normalized text: (text as written, ticked?)} for every tick-box line."""
    found = {}
    for line in markdown.splitlines():
        match = BOX.match(line)
        if match:
            found[normalize(match.group(2))] = (match.group(2), match.group(1) in "xX")
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--template", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--event", type=Path, help="the GitHub event payload (GITHUB_EVENT_PATH)")
    source.add_argument("--body-file", type=Path, help="a file holding the PR body, for local runs")
    args = parser.parse_args()

    required = boxes(args.template.read_text(encoding="utf-8"))
    if not required:
        print("::error::the pull request template has no tick boxes")
        return 1

    if args.event:
        event = json.loads(args.event.read_text(encoding="utf-8"))
        body = (event.get("pull_request") or {}).get("body") or ""
    else:
        body = args.body_file.read_text(encoding="utf-8")
    in_body = boxes(body)

    missing = [key for key in required if not in_body.get(key, ("", False))[1]]
    for key in missing:
        state = "not ticked" if key in in_body else "missing from the description"
        print(f"::error::Pull request box {state}: \"{required[key][0]}\"")
    if missing:
        print(f"{len(missing)} of {len(required)} required boxes are not ticked. "
              "Edit the pull request description and tick them (the check runs again on edit).")
        return 1
    print(f"All {len(required)} required boxes are ticked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
