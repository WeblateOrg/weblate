#!/usr/bin/env python3

# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import sys
from pathlib import Path

from fuzzing.atheris_compat import fuzz, instrument_imports, setup

with instrument_imports():
    from fuzzing.targets import TARGETS


def _resolve_setup_argv(argv: list[str], target_name: str) -> list[str]:
    """Normalize argv so libFuzzer re-execs the target wrapper, not runner.py."""
    if len(argv) <= 1 or argv[1] != target_name:
        return argv

    wrapper_path = Path(argv[0]).with_name(target_name)
    if wrapper_path.is_file() and os.access(wrapper_path, os.X_OK):
        return [str(wrapper_path), *argv[2:]]

    return [argv[0], *argv[2:]]


def resolve_target(argv: list[str]) -> tuple[str, list[str]]:
    """Resolve a target name from argv or wrapper name."""
    if len(argv) > 1 and argv[1] in TARGETS:
        target_name = argv[1]
        return target_name, _resolve_setup_argv(argv, target_name)

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
