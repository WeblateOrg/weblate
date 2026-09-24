# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations


def pgettext_noop(context: str, message: str) -> str:
    return message
