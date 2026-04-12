# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
import sys

import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "weblate.addons.extractors.django.settings"
)


def main() -> None:
    django.setup()

    from weblate.addons.extractors.django.command import Command  # noqa: PLC0415

    Command().run_from_argv(
        [
            sys.executable,
            "weblate-extract-makemessages",
            *sys.argv[1:],
        ]
    )


if __name__ == "__main__":
    main()
