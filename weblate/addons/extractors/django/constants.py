# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DJANGO_IGNORE_PATTERNS = (
    "CVS",
    ".*",
    "*~",
    "*.pyc",
    ".git/*",
    ".venv/*",
    "venv/*",
    "node_modules/*",
    "build/*",
    "dist/*",
    "locale",
    "conf/locale",
)
