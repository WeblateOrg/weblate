#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import argparse
import os
import posixpath
import re
import sys
from pathlib import Path


def parse_numstat_paths(path: Path) -> list[str]:
    paths: list[str] = []
    records = path.read_bytes().split(b"\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue

        fields = record.split(b"\t", 2)
        if len(fields) < 3:
            msg = f"Malformed patch stat record: {record!r}"
            raise ValueError(msg)

        if fields[2]:
            paths.append(os.fsdecode(fields[2]))
            continue

        if index + 1 >= len(records):
            msg = "Malformed rename or copy patch stat record"
            raise ValueError(msg)
        paths.extend((os.fsdecode(records[index]), os.fsdecode(records[index + 1])))
        index += 2

    return paths


def validate_paths(paths: list[str], allowed_pattern: re.Pattern[str]) -> None:
    if not paths:
        msg = "Patch does not touch any files"
        raise ValueError(msg)

    rejected = []
    for path in paths:
        normalized = posixpath.normpath(path)
        if (
            path.startswith("/")
            or normalized == ".."
            or normalized.startswith("../")
            or normalized != path
            or not allowed_pattern.fullmatch(path)
        ):
            rejected.append(path)

    if rejected:
        print("Rejected patch paths:", file=sys.stderr)
        for path in rejected:
            print(f"  {path}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate NUL-delimited git numstat paths against an allowlist."
    )
    parser.add_argument("allowed_pattern", help="Regular expression for allowed paths")
    parser.add_argument("numstat", type=Path, help="NUL-delimited git numstat output")
    args = parser.parse_args()

    paths = parse_numstat_paths(args.numstat)
    validate_paths(paths, re.compile(args.allowed_pattern))

    print("Validated patch paths:")
    for path in paths:
        print(f"  {path}")


if __name__ == "__main__":
    main()
