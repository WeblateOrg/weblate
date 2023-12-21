# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Auto fixes implemented for specific environments and not enabled by default."""

import re

from django.utils.translation import gettext_lazy

from weblate.trans.autofixes.base import AutoFix

QUOTE_PARAM = re.compile(r"'(\{[^}]+\})'")
SINGLE_APO = re.compile(r"'{1,3}")
DOUBLE_APO = re.compile(r"'{4,}")
REPLACEMENT = "__weblate:quote__"
REPLACE_STRING = rf"{REPLACEMENT}\1{REPLACEMENT}"


class DoubleApostrophes(AutoFix):
    """
    Ensures apostrophes are escaped in Java Properties MessageFormat string.

    - all apostrophes except ones around {} vars are doubled

    Note: This fix is not really generically applicable in all cases, that's
    why it's not enabled by default.
    """

    fix_id = "java-messageformat"
    name = gettext_lazy("Apostrophes in Java MessageFormat")

    def fix_single_target(self, target, source, unit):
        flags = unit.all_flags
        if ("auto-java-messageformat" not in flags or "{0" not in source) and (
            "java-format" not in flags
        ):
            return target, False
        # Split on apostrophe
        new = SINGLE_APO.sub(
            "''", DOUBLE_APO.sub("''''", QUOTE_PARAM.sub(REPLACE_STRING, target))
        ).replace(REPLACEMENT, "'")
        return new, new != target
