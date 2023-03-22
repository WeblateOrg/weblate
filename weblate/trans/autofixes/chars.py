# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils.translation import gettext_lazy as _

from weblate.formats.helpers import CONTROLCHARS_TRANS
from weblate.trans.autofixes.base import AutoFix


class ReplaceTrailingDotsWithEllipsis(AutoFix):
    """Replace trailing dots with an ellipsis."""

    fix_id = "end-ellipsis"
    name = _("Trailing ellipsis")

    def fix_single_target(self, target, source, unit):
        if source and source[-1] == "…" and target.endswith("..."):
            return f"{target[:-3]}…", True
        return target, False


class RemoveZeroSpace(AutoFix):
    """Remove zero width space if there is none in the source."""

    fix_id = "zero-width-space"
    name = _("Zero-width space")

    def fix_single_target(self, target, source, unit):
        if unit.translation.language.base_code == "km":
            return target, False
        if "\u200b" not in source and "\u200b" in target:
            return target.replace("\u200b", ""), True
        return target, False


class RemoveControlChars(AutoFix):
    """Remove control characters from the string."""

    fix_id = "control-chars"
    name = _("Control characters")

    def fix_single_target(self, target, source, unit):
        result = target.translate(CONTROLCHARS_TRANS)
        return result, result != target
