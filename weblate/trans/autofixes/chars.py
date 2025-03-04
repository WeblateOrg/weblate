# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy

from weblate.checks.chars import (
    FRENCH_PUNCTUATION_FIXUP_RE_NBSP,
    FRENCH_PUNCTUATION_FIXUP_RE_NNBSP,
    EndEllipsisCheck,
    PunctuationSpacingCheck,
    ZeroWidthSpaceCheck,
)
from weblate.checks.same import RST_MATCH
from weblate.formats.helpers import CONTROLCHARS_TRANS
from weblate.trans.autofixes.base import AutoFix

if TYPE_CHECKING:
    from weblate.trans.models import Unit


class ReplaceTrailingDotsWithEllipsis(AutoFix):
    """Replace trailing dots with an ellipsis."""

    fix_id = "end-ellipsis"
    name = gettext_lazy("Trailing ellipsis")

    @staticmethod
    def get_related_checks():
        return [EndEllipsisCheck()]

    def fix_single_target(
        self, target: str, source: str, unit: Unit
    ) -> tuple[str, bool]:
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

    def fix_single_target(
        self, target: str, source: str, unit: Unit
    ) -> tuple[str, bool]:
        if unit.translation.language.base_code == "km":
            return target, False
        if "\u200b" not in source and "\u200b" in target:
            return target.replace("\u200b", ""), True
        return target, False


class RemoveControlChars(AutoFix):
    """Remove control characters from the string."""

    fix_id = "control-chars"
    name = gettext_lazy("Control characters")

    def fix_single_target(
        self, target: str, source: str, unit: Unit
    ) -> tuple[str, bool]:
        result = target.translate(CONTROLCHARS_TRANS)
        return result, result != target


class DevanagariDanda(AutoFix):
    """Fixes Bangla sentence ender."""

    fix_id = "devanadari-danda"
    name = gettext_lazy("Devanagari danda")

    def fix_single_target(
        self, target: str, source: str, unit: Unit
    ) -> tuple[str, bool]:
        if (
            unit.translation.language.is_base({"hi", "bn", "or"})
            and "_Latn" not in unit.translation.language.code
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

    def fix_single_target(
        self, target: str, source: str, unit: Unit
    ) -> tuple[str, bool]:
        def spacing_replace(matchobj: re.Match) -> str:
            if "rst-text" in unit.all_flags:
                offset = matchobj.start(2)
                rst_position = RST_MATCH.search(target, offset)
                if rst_position is not None and rst_position.start(0) == offset:
                    # Skip escaping inside rst tag
                    return matchobj.group(0)
            return f"\u00a0{matchobj.group(2)}"

        if (
            unit.translation.language.is_base({"fr"})
            and unit.translation.language.code != "fr_CA"
            and "ignore-punctuation-spacing" not in unit.all_flags
        ):
            # Fix existing
            new_target = re.sub(
                FRENCH_PUNCTUATION_FIXUP_RE_NBSP, spacing_replace, target
            )
            new_target = re.sub(
                FRENCH_PUNCTUATION_FIXUP_RE_NNBSP, "\u202f\\2", new_target
            )
            # Do not add missing as that is likely to trigger issues with other content
            # such as URLs or Markdown syntax.
            return new_target, new_target != target
        return target, False
