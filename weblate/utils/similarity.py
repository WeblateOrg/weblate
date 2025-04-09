# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from rapidfuzz import fuzz


class Comparer:
    """
    String comparer abstraction.

    The reason is to be able to change implementation.
    """

    def similarity(self, first: str, second: str) -> int:
        """Return string similarity in range 0 - 100%."""
        return int(fuzz.QRatio(first, second))
