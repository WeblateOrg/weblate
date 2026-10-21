#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check source lengths of unindented reStructuredText heading adornments."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ADORNMENT = re.compile(r"([=+~^*`#-])\1*")


def report_error(path: Path, line: int, message: str) -> None:
    """Emit a GitHub Actions annotation or a local diagnostic."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        filename = (
            str(path)
            .replace("%", "%25")
            .replace("\r", "%0D")
            .replace("\n", "%0A")
            .replace(":", "%3A")
            .replace(",", "%2C")
        )
        message = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error file={filename},line={line}::{message}")
    else:
        print(f"{path}:{line}: {message}")


def check_file(path: Path) -> bool:
    """Report mismatched adornments and return whether the file failed."""
    lines = path.read_text(encoding="utf-8").splitlines()
    failed = False
    for index, title in enumerate(lines[:-1]):
        if not title or title[0].isspace() or not re.search(r"\w", title):
            continue
        underline = lines[index + 1]
        if not ADORNMENT.fullmatch(underline):
            continue

        overline = lines[index - 1] if index else ""
        if overline and not ADORNMENT.fullmatch(overline):
            continue

        adornments = [index + 1]
        if overline and overline[0] == underline[0]:
            adornments.insert(0, index - 1)
        for position in adornments:
            actual = len(lines[position])
            expected = len(title)
            if actual != expected:
                report_error(
                    path,
                    position + 1,
                    f"heading adornment has {actual} characters; expected {expected}",
                )
                failed = True
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filenames", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    for path in args.filenames:
        failed = check_file(path) or failed
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
