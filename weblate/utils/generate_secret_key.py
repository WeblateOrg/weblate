#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.utils.crypto import get_random_string


def main(argv: list[str] | None = None, developer_mode: bool = False) -> None:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)"
    print(get_random_string(50, chars))


if __name__ == "__main__":
    main()
