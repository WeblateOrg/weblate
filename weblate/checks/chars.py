#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


from django.utils.translation import gettext_lazy as _

from weblate.checks.base import CountingCheck, TargetCheck, TargetCheckParametrized
from weblate.checks.markup import strip_entities
from weblate.checks.parser import single_value_flag

KASHIDA_CHARS = (
    "\u0640",
    "\uFCF2",
    "\uFCF3",
    "\uFCF4",
    "\uFE71",
    "\uFE77",
    "\uFE79",
    "\uFE7B",
    "\uFE7D",
    "\uFE7F",
)
FRENCH_PUNCTUATION = {";", ":", "?", "!"}


class BeginNewlineCheck(TargetCheck):
    """Check for newlines at beginning."""

    check_id = "begin_newline"
    name = _("Starting newline")
    description = _("Source and translation do not both start with a newline")

    def check_single(self, source, target, unit):
        return self.check_chars(source, target, 0, ["\n"])


class EndNewlineCheck(TargetCheck):
    """Check for newlines at end."""

    check_id = "end_newline"
    name = _("Trailing newline")
    description = _("Source and translation do not both end with a newline")

    def check_single(self, source, target, unit):
        return self.check_chars(source, target, -1, ["\n"])


class BeginSpaceCheck(TargetCheck):
    """Whitespace check, starting whitespace usually is important for UI."""

    check_id = "begin_space"
    name = _("Starting spaces")
    description = _(
        "Source and translation do not both start with same number of spaces"
    )

    def check_single(self, source, target, unit):
        # One letter things are usually decimal/thousand separators
        if len(source) <= 1 and len(target) <= 1:
            return False

        stripped_target = target.lstrip(" ")
        stripped_source = source.lstrip(" ")

        # String translated to spaces only
        if not stripped_target:
            return False

        # Count space chars in source and target
        source_space = len(source) - len(stripped_source)
        target_space = len(target) - len(stripped_target)

        # Compare numbers
        return source_space != target_space

    def get_fixup(self, unit):
        source = unit.source_string
        stripped_source = source.lstrip(" ")
        spaces = len(source) - len(stripped_source)
        if spaces:
            replacement = source[:spaces]
        else:
            replacement = ""
        return [("^ *", replacement, "u")]


class EndSpaceCheck(TargetCheck):
    """Whitespace check."""

    check_id = "end_space"
    name = _("Trailing space")
    description = _("Source and translation do not both end with a space")

    def check_single(self, source, target, unit):
        # One letter things are usually decimal/thousand separators
        if len(source) <= 1 and len(target) <= 1:
            return False
        if not source or not target:
            return False

        stripped_target = target.rstrip(" ")
        stripped_source = source.rstrip(" ")

        # String translated to spaces only
        if not stripped_target:
            return False

        # Count space chars in source and target
        source_space = len(source) - len(stripped_source)
        target_space = len(target) - len(stripped_target)

        # Compare numbers
        return source_space != target_space

    def get_fixup(self, unit):
        source = unit.source_string
        stripped_source = source.rstrip(" ")
        spaces = len(source) - len(stripped_source)
        if spaces:
            replacement = source[-spaces:]
        else:
            replacement = ""
        return [(" *$", replacement, "u")]


class DoubleSpaceCheck(TargetCheck):
    """Doublespace check."""

    check_id = "double_space"
    name = _("Double space")
    description = _("Translation contains double space")

    def check_single(self, source, target, unit):
        # One letter things are usually decimal/thousand separators
        if len(source) <= 1 and len(target) <= 1:
            return False
        if not source or not target:
            return False
        if "  " in source:
            return False
        # Check if target contains double space
        return "  " in target

    def get_fixup(self, unit):
        return [(" {2,}", " ")]


class EndStopCheck(TargetCheck):
    """Check for final stop."""

    check_id = "end_stop"
    name = _("Mismatched full stop")
    description = _("Source and translation do not both end with a full stop")

    def check_single(self, source, target, unit):
        if len(source) <= 4:
            # Might need to use shortcut in translation
            return False
        if not target:
            return False
        # Thai and Lojban does not have a full stop
        if self.is_language(unit, ("th", "jbo")):
            return False
        # Allow ... to be translated into ellipsis
        if source.endswith("...") and target[-1] == "…":
            return False
        if self.is_language(unit, ("ja",)) and source[-1] in (":", ";"):
            # Japanese sentence might need to end with full stop
            # in case it's used before list.
            return self.check_chars(source, target, -1, (";", ":", "：", ".", "。"))
        if self.is_language(unit, ("hy",)):
            return self.check_chars(
                source,
                target,
                -1,
                (".", "。", "।", "۔", "։", "·", "෴", "។", ":", "՝", "?", "!", "`"),
            )
        if self.is_language(unit, ("hi", "bn", "or")):
            # Using | instead of । is not typographically correct, but
            # seems to be quite usual. \u0964 is correct, but \u09F7
            # is also sometimes used instead in some popular editors.
            return self.check_chars(source, target, -1, (".", "\u0964", "\u09F7", "|"))
        if self.is_language(unit, ("sat",)):
            # Santali uses "᱾" as full stop
            return self.check_chars(source, target, -1, (".", "᱾"))
        return self.check_chars(
            source, target, -1, (".", "。", "।", "۔", "։", "·", "෴", "។")
        )


class EndColonCheck(TargetCheck):
    """Check for final colon."""

    check_id = "end_colon"
    name = _("Mismatched colon")
    description = _("Source and translation do not both end with a colon")

    def _check_hy(self, source, target):
        if source[-1] == ":":
            return self.check_chars(source, target, -1, (":", "՝", "`"))
        return False

    def _check_ja(self, source, target):
        # Japanese sentence might need to end with full stop
        # in case it's used before list.
        if source[-1] in (":", ";"):
            return self.check_chars(source, target, -1, (";", ":", "：", ".", "。"))
        return False

    def check_single(self, source, target, unit):
        if not source or not target:
            return False
        if self.is_language(unit, ("jbo",)):
            return False
        if self.is_language(unit, ("hy",)):
            return self._check_hy(source, target)
        if self.is_language(unit, ("ja",)):
            return self._check_ja(source, target)
        return self.check_chars(source, target, -1, (":", "：", "៖"))


class EndQuestionCheck(TargetCheck):
    """Check for final question mark."""

    check_id = "end_question"
    name = _("Mismatched question mark")
    description = _("Source and translation do not both end with a question mark")
    question_el = ("?", ";", ";")

    def _check_hy(self, source, target):
        if source[-1] == "?":
            return self.check_chars(source, target, -1, ("?", "՞", "։"))
        return False

    def _check_el(self, source, target):
        if source[-1] != "?":
            return False
        return target[-1] not in self.question_el

    def check_single(self, source, target, unit):
        if not source or not target:
            return False
        if self.is_language(unit, ("jbo",)):
            return False
        if self.is_language(unit, ("hy",)):
            return self._check_hy(source, target)
        if self.is_language(unit, ("el",)):
            return self._check_el(source, target)

        return self.check_chars(
            source, target, -1, ("?", "՞", "؟", "⸮", "？", "፧", "꘏", "⳺")
        )


class EndExclamationCheck(TargetCheck):
    """Check for final exclamation mark."""

    check_id = "end_exclamation"
    name = _("Mismatched exclamation mark")
    description = _("Source and translation do not both end with an exclamation mark")

    def check_single(self, source, target, unit):
        if not source or not target:
            return False
        if (
            self.is_language(unit, ("eu",))
            and source[-1] == "!"
            and "¡" in target
            and "!" in target
        ):
            return False
        if self.is_language(unit, ("hy", "jbo")):
            return False
        if source.endswith("Texy!") or target.endswith("Texy!"):
            return False
        return self.check_chars(source, target, -1, ("!", "！", "՜", "᥄", "႟", "߹"))


class EndEllipsisCheck(TargetCheck):
    """Check for ellipsis at the end of string."""

    check_id = "end_ellipsis"
    name = _("Mismatched ellipsis")
    description = _("Source and translation do not both end with an ellipsis")

    def check_single(self, source, target, unit):
        if not target:
            return False
        if self.is_language(unit, ("jbo",)):
            return False
        # Allow ... to be translated into ellipsis
        if source.endswith("...") and target[-1] == "…":
            return False
        return self.check_chars(source, target, -1, ("…",))


class EscapedNewlineCountingCheck(CountingCheck):
    r"""Check whether there is same amount of escaped \n strings."""

    string = "\\n"
    check_id = "escaped_newline"
    name = _("Mismatched \\n")
    description = _("Number of \\n in translation does not match source")


class NewLineCountCheck(CountingCheck):
    """Check whether there is same amount of new lines."""

    string = "\n"
    check_id = "newline-count"
    name = _("Mismatching line breaks")
    description = _("Number of new lines in translation does not match source")


class ZeroWidthSpaceCheck(TargetCheck):
    """Check for zero width space char (<U+200B>)."""

    check_id = "zero-width-space"
    name = _("Zero-width space")
    description = _("Translation contains extra zero-width space character")

    def check_single(self, source, target, unit):
        if self.is_language(unit, ("km",)):
            return False
        if "\u200b" in source:
            return False
        return "\u200b" in target

    def get_fixup(self, unit):
        return [("\u200b", "", "gu")]


class MaxLengthCheck(TargetCheckParametrized):
    """Check for maximum length of translation."""

    check_id = "max-length"
    name = _("Maximum length of translation")
    description = _("Translation should not exceed given length")
    default_disabled = True

    @property
    def param_type(self):
        return single_value_flag(int)

    def check_target_params(self, sources, targets, unit, value):
        replace = self.get_replacement_function(unit)
        return any(len(replace(target)) > value for target in targets)


class EndSemicolonCheck(TargetCheck):
    """Check for semicolon at end."""

    check_id = "end_semicolon"
    name = _("Mismatched semicolon")
    description = _("Source and translation do not both end with a semicolon")

    def check_single(self, source, target, unit):
        if self.is_language(unit, ("el",)) and source and source[-1] == "?":
            # Complement to question mark check
            return False
        return self.check_chars(
            strip_entities(source), strip_entities(target), -1, [";"]
        )


class KashidaCheck(TargetCheck):
    check_id = "kashida"
    name = _("Kashida letter used")
    description = _("The decorative kashida letters should not be used")

    def check_single(self, source, target, unit):
        return any(x in target for x in KASHIDA_CHARS)

    def get_fixup(self, unit):
        return [("[{}]".format("".join(KASHIDA_CHARS)), "", "gu")]


class PunctuationSpacingCheck(TargetCheck):
    check_id = "punctuation_spacing"
    name = _("Punctuation spacing")
    description = _("Missing non breakable space before double punctuation sign")

    def check_single(self, source, target, unit):
        if (
            not self.is_language(unit, ("fr", "br"))
            or unit.translation.language.code == "fr_CA"
        ):
            return False

        # Remove XML/HTML entities to simplify parsing
        target = strip_entities(target)

        whitespace = {" ", "\u00A0", "\u202F", "\u2009"}

        total = len(target)
        for i, char in enumerate(target):
            if char in FRENCH_PUNCTUATION:
                if i + 1 < total and not target[i + 1].isspace():
                    continue
                if i == 0 or target[i - 1] not in whitespace:
                    return True
        return False

    def get_fixup(self, unit):
        return [
            # First fix possibly wrong whitespace
            (
                "([ \u00A0\u2009])([{}])".format("".join(FRENCH_PUNCTUATION)),
                "\u202F$2",
                "gu",
            ),
            # Then add missing ones
            (
                "([^\u202F])([{}])".format("".join(FRENCH_PUNCTUATION)),
                "$1\u202F$2",
                "gu",
            ),
        ]
