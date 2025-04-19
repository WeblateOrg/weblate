# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy

from weblate.checks.base import CountingCheck, TargetCheck, TargetCheckParametrized
from weblate.checks.markup import strip_entities
from weblate.checks.parser import single_value_flag
from weblate.checks.same import strip_format

if TYPE_CHECKING:
    from collections.abc import Iterable

    from weblate.trans.models import Unit

FRENCH_PUNCTUATION_NBSP = {":"}
FRENCH_PUNCTUATION_NNBSP = {";", "?", "!"}
FRENCH_PUNCTUATION = FRENCH_PUNCTUATION_NBSP.union(FRENCH_PUNCTUATION_NNBSP)
FRENCH_PUNCTUATION_SPACING = {"Zs", "Ps", "Pe"}
FRENCH_PUNCTUATION_FIXUP_RE_NBSP = "([ \u2009\u202f])([{}])".format(
    "".join(FRENCH_PUNCTUATION_NBSP)
)
FRENCH_PUNCTUATION_FIXUP_RE_NNBSP = "([ \u00a0\u2009])([{}])".format(
    "".join(FRENCH_PUNCTUATION_NNBSP)
)
FRENCH_PUNCTUATION_MISSING_RE_NBSP = "([^\u00a0])([{}])".format(
    "".join(FRENCH_PUNCTUATION_NBSP)
)
FRENCH_PUNCTUATION_MISSING_RE_NNBSP = "([^\u202f])([{}])".format(
    "".join(FRENCH_PUNCTUATION_NNBSP)
)
MY_QUESTION_MARK = "\u1038\u104b"
INTERROBANGS = ("?!", "!?", "？！", "！？", "⁈", "⁉")


class BeginNewlineCheck(TargetCheck):
    """Check for newlines at beginning."""

    check_id = "begin_newline"
    name = gettext_lazy("Starting newline")
    description = gettext_lazy(
        "Source and translation do not both start with a newline."
    )

    def check_single(self, source: str, target: str, unit: Unit):
        return self.check_chars(source, target, 0, {"\n"})


class EndNewlineCheck(TargetCheck):
    """Check for newlines at end."""

    check_id = "end_newline"
    name = gettext_lazy("Trailing newline")
    description = gettext_lazy("Source and translation do not both end with a newline.")

    def check_single(self, source: str, target: str, unit: Unit):
        return self.check_chars(source, target, -1, {"\n"})


class BeginSpaceCheck(TargetCheck):
    """Whitespace check, starting whitespace usually is important for UI."""

    check_id = "begin_space"
    name = gettext_lazy("Starting spaces")
    description = gettext_lazy(
        "Source and translation do not both start with same number of spaces."
    )

    def check_single(self, source: str, target: str, unit: Unit):
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

    def get_fixup(self, unit: Unit):
        source = unit.source_string
        stripped_source = source.lstrip(" ")
        spaces = len(source) - len(stripped_source)
        replacement = source[:spaces] if spaces else ""
        return [("^ *", replacement, "u")]


class EndSpaceCheck(TargetCheck):
    """Whitespace check."""

    check_id = "end_space"
    name = gettext_lazy("Trailing space")
    description = gettext_lazy("Source and translation do not both end with a space.")

    def check_single(self, source: str, target: str, unit: Unit):
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

    def get_fixup(self, unit: Unit):
        source = unit.source_string
        stripped_source = source.rstrip(" ")
        spaces = len(source) - len(stripped_source)
        replacement = source[-spaces:] if spaces else ""
        return [(" *$", replacement, "u")]


class DoubleSpaceCheck(TargetCheck):
    """Doublespace check."""

    check_id = "double_space"
    name = gettext_lazy("Double space")
    description = gettext_lazy("Translation contains double space.")

    def check_single(self, source: str, target: str, unit: Unit):
        # One letter things are usually decimal/thousand separators
        if len(source) <= 1 and len(target) <= 1:
            return False
        if not source or not target:
            return False
        if "  " in source:
            return False
        # Check if target contains double space
        return "  " in target

    def get_fixup(self, unit: Unit):
        return [(" {2,}", " ")]


class EndStopCheck(TargetCheck):
    """Check for final stop."""

    check_id = "end_stop"
    name = gettext_lazy("Mismatched full stop")
    description = gettext_lazy(
        "Source and translation do not both end with a full stop."
    )

    def _check_my(self, source: str, target: str):
        if target.endswith(MY_QUESTION_MARK):
            # Laeave this on the question mark check
            return False
        return self.check_chars(source, target, -1, {".", "။"})

    def should_skip(self, unit: Unit) -> bool:
        # Thai and Lojban does not have a full stop
        if unit.translation.language.is_base({"th", "jbo"}):
            return True
        return super().should_skip(unit)

    def check_single(self, source: str, target: str, unit: Unit):
        if len(source) <= 4:
            # Might need to use shortcut in translation
            return False
        if not target:
            return False
        # Allow ... to be translated into ellipsis
        if source.endswith("...") and target[-1] == "…":
            return False
        if unit.translation.language.is_cjk() and source[-1] in {":", ";"}:
            # Japanese sentence might need to end with full stop
            # in case it's used before list.
            return self.check_chars(source, target, -1, {";", ":", "：", ".", "。"})
        if unit.translation.language.is_base({"hy"}):
            return self.check_chars(
                source,
                target,
                -1,
                {".", "。", "।", "۔", "։", "·", "෴", "។", ":", "՝", "?", "!", "`"},
            )
        if unit.translation.language.is_base({"hi", "bn", "or"}):
            # Using | instead of । is not typographically correct, but
            # seems to be quite usual. \u0964 is correct, but \u09F7
            # is also sometimes used instead in some popular editors.
            return self.check_chars(source, target, -1, {".", "\u0964", "\u09f7", "|"})
        if unit.translation.language.is_base({"sat"}):
            # Santali uses "᱾" as full stop
            return self.check_chars(source, target, -1, {".", "᱾"})
        if unit.translation.language.is_base({"my"}):
            return self._check_my(source, target)
        return self.check_chars(
            source, target, -1, {".", "。", "।", "۔", "։", "·", "෴", "។", "።"}
        )


class EndColonCheck(TargetCheck):
    """Check for final colon."""

    check_id = "end_colon"
    name = gettext_lazy("Mismatched colon")
    description = gettext_lazy("Source and translation do not both end with a colon.")

    def should_skip(self, unit: Unit) -> bool:
        # Thai and Lojban does not have a colon
        if unit.translation.language.is_base({"th", "jbo"}):
            return True
        return super().should_skip(unit)

    def _check_hy(self, source: str, target: str):
        if source[-1] == ":":
            return self.check_chars(source, target, -1, {":", "՝", "`"})
        return False

    def _check_ja(self, source: str, target: str):
        # Japanese sentence might need to end with full stop
        # in case it's used before list.
        if source[-1] in {":", ";"}:
            return self.check_chars(source, target, -1, {";", ":", "：", ".", "。"})
        return False

    def check_single(self, source: str, target: str, unit: Unit):
        if not source or not target:
            return False
        if unit.translation.language.is_base({"hy"}):
            return self._check_hy(source, target)
        if unit.translation.language.is_cjk():
            return self._check_ja(source, target)
        return self.check_chars(source, target, -1, {":", "：", "៖"})


class EndQuestionCheck(TargetCheck):
    """Check for final question mark."""

    check_id = "end_question"
    name = gettext_lazy("Mismatched question mark")
    description = gettext_lazy(
        "Source and translation do not both end with a question mark."
    )
    question_el = ("?", ";", ";")

    def should_skip(self, unit: Unit) -> bool:
        # Thai and Lojban does not have a question mark
        if unit.translation.language.is_base({"th", "jbo"}):
            return True
        return super().should_skip(unit)

    def _check_hy(self, source: str, target: str):
        if source[-1] == "?":
            return self.check_chars(source, target, -1, {"?", "՞", "։"})
        return False

    def _check_el(self, source: str, target: str):
        if source[-1] != "?":
            return False
        return target[-1] not in self.question_el

    def _check_my(self, source: str, target: str):
        return source.endswith("?") != target.endswith(MY_QUESTION_MARK)

    def check_single(self, source: str, target: str, unit: Unit):
        if not source or not target:
            return False
        if source.endswith(INTERROBANGS) or target.endswith(INTERROBANGS):
            return False
        if unit.translation.language.is_base({"hy"}):
            return self._check_hy(source, target)
        if unit.translation.language.is_base({"el"}):
            return self._check_el(source, target)
        if unit.translation.language.is_base({"my"}):
            return self._check_my(source, target)

        return self.check_chars(
            source, target, -1, {"?", "՞", "؟", "⸮", "？", "፧", "꘏", "⳺"}
        )


class EndExclamationCheck(TargetCheck):
    """Check for final exclamation mark."""

    check_id = "end_exclamation"
    name = gettext_lazy("Mismatched exclamation mark")
    description = gettext_lazy(
        "Source and translation do not both end with an exclamation mark."
    )

    def should_skip(self, unit: Unit) -> bool:
        # Thai and Lojban and Armenian does not have an exclamation mark
        if unit.translation.language.is_base({"hy", "th", "jbo"}):
            return True
        return super().should_skip(unit)

    def check_single(self, source: str, target: str, unit: Unit):
        if not source or not target:
            return False
        if source.endswith(INTERROBANGS) or target.endswith(INTERROBANGS):
            return False
        if (
            unit.translation.language.is_base({"eu"})
            and source[-1] == "!"
            and "¡" in target
            and "!" in target
        ):
            return False
        if unit.translation.language.is_base({"my"}):
            return self.check_chars(source, target, -1, {"!", "႟"})
        if source.endswith("Texy!") or target.endswith("Texy!"):
            return False
        return self.check_chars(source, target, -1, {"!", "！", "՜", "᥄", "႟", "߹"})


class EndInterrobangCheck(TargetCheck):
    """Check for final interrobang expression."""

    check_id = "end_interrobang"
    name = gettext_lazy("Mismatched interrobang")
    description = gettext_lazy(
        "Source and translation do not both end with an interrobang expression."
    )

    def check_single(self, source: str, target: str, unit: Unit):
        if not source or not target:
            return False

        return source.endswith(INTERROBANGS) != target.endswith(INTERROBANGS)


class EndEllipsisCheck(TargetCheck):
    """Check for ellipsis at the end of string."""

    check_id = "end_ellipsis"
    name = gettext_lazy("Mismatched ellipsis")
    description = gettext_lazy(
        "Source and translation do not both end with an ellipsis."
    )

    def should_skip(self, unit: Unit) -> bool:
        # Thai and Lojban does not have a ellipsis
        if unit.translation.language.is_base({"th", "jbo"}):
            return True
        return super().should_skip(unit)

    def check_single(self, source: str, target: str, unit: Unit):
        if not target:
            return False
        # Allow ... to be translated into ellipsis
        if source.endswith("...") and target[-1] == "…":
            return False
        return self.check_chars(source, target, -1, {"…"})


class EscapedNewlineCountingCheck(CountingCheck):
    r"""Check whether there is same amount of escaped \n strings."""

    string = "\\n"
    check_id = "escaped_newline"
    name = gettext_lazy("Mismatched \\n")
    description = gettext_lazy(
        "Number of \\n literals in translation does not match source."
    )

    ignore_re = re.compile(r"[A-Z]:\\\\[^\\ ]+(\\[^\\ ]+)+")

    def check_single(self, source: str, target: str, unit: Unit):
        if not target or not source:
            return False

        target = self.ignore_re.sub("", target)
        source = self.ignore_re.sub("", source)
        return super().check_single(source, target, unit)


class NewLineCountCheck(CountingCheck):
    """Check whether there is same amount of new lines."""

    string = "\n"
    check_id = "newline-count"
    name = gettext_lazy("Mismatching line breaks")
    description = gettext_lazy(
        "Number of new lines in translation does not match source."
    )


class ZeroWidthSpaceCheck(TargetCheck):
    """Check for zero width space char (<U+200B>)."""

    check_id = "zero-width-space"
    name = gettext_lazy("Zero-width space")
    description = gettext_lazy("Translation contains extra zero-width space character.")

    def check_single(self, source: str, target: str, unit: Unit):
        if unit.translation.language.is_base({"km"}):
            return False
        if "\u200b" in source:
            return False
        return "\u200b" in target

    def get_fixup(self, unit: Unit):
        return [("\u200b", "", "gu")]


class MaxLengthCheck(TargetCheckParametrized):
    """Check for maximum length of translation."""

    check_id = "max-length"
    name = gettext_lazy("Maximum length of translation")
    description = gettext_lazy("Translation should not exceed given length.")
    default_disabled = True

    @property
    def param_type(self):
        return single_value_flag(int)

    def check_target_params(
        self, sources: list[str], targets: list[str], unit: Unit, value
    ):
        replace = self.get_replacement_function(unit)
        return any(len(replace(target)) > value for target in targets)


class EndSemicolonCheck(TargetCheck):
    """Check for semicolon at end."""

    check_id = "end_semicolon"
    name = gettext_lazy("Mismatched semicolon")
    description = gettext_lazy(
        "Source and translation do not both end with a semicolon."
    )

    def check_single(self, source: str, target: str, unit: Unit):
        if unit.translation.language.is_base({"el"}) and source and source[-1] == "?":
            # Complement to question mark check
            return False
        return self.check_chars(
            strip_entities(source), strip_entities(target), -1, {";"}
        )


class KashidaCheck(TargetCheck):
    check_id = "kashida"
    name = gettext_lazy("Kashida letter used")
    description = gettext_lazy("The decorative kashida letters should not be used.")

    kashida_regex = (
        # Allow kashida after certain letters
        "(?<![\u0628\u0643\u0644])"
        # List of kashida letters to check
        "[\u0640\ufcf2\ufcf3\ufcf4\ufe71\ufe77\ufe79\ufe7b\ufe7d\ufe7f]"
    )
    kashida_re = re.compile(kashida_regex)

    def check_single(self, source: str, target: str, unit: Unit):
        return self.kashida_re.search(target)

    def get_fixup(self, unit: Unit):
        return [(self.kashida_regex, "", "gu")]


class PunctuationSpacingCheck(TargetCheck):
    check_id = "punctuation_spacing"
    name = gettext_lazy("Punctuation spacing")
    description = gettext_lazy(
        "Missing non breakable space before double punctuation sign."
    )

    def should_skip(self, unit: Unit) -> bool:
        if (
            not unit.translation.language.is_base({"fr"})
            or unit.translation.language.code == "fr_CA"
        ):
            return True
        return super().should_skip(unit)

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        # Remove possible markup
        target = strip_format(target, unit.all_flags)
        # Remove XML/HTML entities to simplify parsing
        target = strip_entities(target)

        whitespace = {" ", "\u00a0", "\u202f", "\u2009"}

        total = len(target)
        for i, char in enumerate(target):
            if char in FRENCH_PUNCTUATION:
                if i == 0:
                    # Trigger if punctionation at beginning of the string
                    return True
                if (
                    i + 1 < total
                    and unicodedata.category(target[i + 1])
                    not in FRENCH_PUNCTUATION_SPACING
                ):
                    # Ignore when not followed by space or open/close bracket
                    continue
                prev_char = target[i - 1]
                if prev_char not in whitespace and prev_char not in FRENCH_PUNCTUATION:
                    return True
        return False

    def get_fixup(self, unit: Unit) -> Iterable[tuple[str, str, str]] | None:
        return [
            # First fix possibly wrong whitespace
            (
                FRENCH_PUNCTUATION_FIXUP_RE_NBSP,
                "\u00a0$2",
                "gu",
            ),
            (
                FRENCH_PUNCTUATION_FIXUP_RE_NNBSP,
                "\u202f$2",
                "gu",
            ),
            # Then add missing ones
            (
                FRENCH_PUNCTUATION_MISSING_RE_NBSP,
                "$1\u00a0$2",
                "gu",
            ),
            (
                FRENCH_PUNCTUATION_MISSING_RE_NNBSP,
                "$1\u202f$2",
                "gu",
            ),
        ]
