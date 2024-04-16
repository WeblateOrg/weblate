# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from django.utils.translation import gettext_lazy

from weblate.checks.chars import (
    FRENCH_PUNCTUATION_FIXUP_RE,
    EndEllipsisCheck,
    PunctuationSpacingCheck,
    ZeroWidthSpaceCheck,
)
from weblate.formats.helpers import CONTROLCHARS_TRANS
from weblate.trans.autofixes.base import AutoFix


class ReplaceTrailingDotsWithEllipsis(AutoFix):
    """Replace trailing dots with an ellipsis."""

    fix_id = "end-ellipsis"
    name = gettext_lazy("Trailing ellipsis")

    @staticmethod
    def get_related_checks():
        return [EndEllipsisCheck()]

    def fix_single_target(self, target, source, unit):
        if source and source[-1] == "…" and target.endswith("..."):
            return f"{target[:-3]}…", True
        return target, False


class RemoveZeroSpace(AutoFix):
    """Remove zero width space if there is none in the source."""

    fix_id = "zero-width-space"
    name = gettext_lazy("Zero-width space")

    @staticmethod
    def get_related_checks():
        return [ZeroWidthSpaceCheck()]

    def fix_single_target(self, target, source, unit):
        if unit.translation.language.base_code == "km":
            return target, False
        if "\u200b" not in source and "\u200b" in target:
            return target.replace("\u200b", ""), True
        return target, False


class RemoveControlChars(AutoFix):
    """Remove control characters from the string."""

    fix_id = "control-chars"
    name = gettext_lazy("Control characters")

    def fix_single_target(self, target, source, unit):
        result = target.translate(CONTROLCHARS_TRANS)
        return result, result != target


class DevanagariDanda(AutoFix):
    """Fixes Bangla sentence ender."""

    fix_id = "devanadari-danda"
    name = gettext_lazy("Devanagari danda")

    def fix_single_target(self, target, source, unit):
        if (
            unit.translation.language.is_base(("hi", "bn", "or"))
            and source.endswith(".")
            and target.endswith((".", "\u09f7", "|"))
        ):
            return f"{target[:-1]}\u0964", True
        return target, False


class PunctuationSpacing(AutoFix):
    """Ensures French and Breton use correct punctuation spacing."""

    fix_id = "punctuation-spacing"
    name = gettext_lazy("Punctuation spacing")

    @staticmethod
    def get_related_checks():
        return [PunctuationSpacingCheck()]

    def fix_single_target(self, target, source, unit):
        if (
            unit.translation.language.is_base(("fr", "br"))
            and unit.translation.language.code != "fr_CA"
            and "ignore-punctuation-spacing" not in unit.all_flags
        ):
            # Fix existing
            new_target = re.sub(FRENCH_PUNCTUATION_FIXUP_RE, "\u202f\\2", target)
            # Do not add missing as that is likely to trigger issues with other content
            # such as URLs or Markdown syntax.
            return new_target, new_target != target
        return target, False
