#!/usr/bin/env python3
# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Run the isolated search benchmark; see --help for setup and examples."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import django


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "weblate.settings_test")
    django.setup()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Django must initialize before importing the benchmark's model classes.
    from weblate.utils.search_benchmark import main as run  # ruff: ignore[import-outside-top-level]

    run()


if __name__ == "__main__":
    main()
