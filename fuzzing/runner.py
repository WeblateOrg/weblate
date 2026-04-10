#!/usr/bin/env python3

# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import sys
from pathlib import Path

from fuzzing.atheris_compat import fuzz, instrument_imports, setup

with instrument_imports():
    from fuzzing.targets import TARGETS


def resolve_target(argv: list[str]) -> tuple[str, list[str]]:
    """Resolve a target name from argv or wrapper name."""
    if len(argv) > 1 and argv[1] in TARGETS:
        return argv[1], [argv[0], *argv[2:]]

    target = Path(argv[0]).name
    if target in TARGETS:
        return target, argv

    msg = f"Unknown fuzz target {target!r}. Available targets: {', '.join(sorted(TARGETS))}"
    raise SystemExit(msg)


def main() -> None:
    target_name, argv = resolve_target(sys.argv)
    setup(argv, TARGETS[target_name])
    fuzz()


if __name__ == "__main__":
    main()
