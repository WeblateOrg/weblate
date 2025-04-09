# Copyright © Henry Wilkes <henry@torproject.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.utils.html import escape, format_html, format_html_join
from django.utils.safestring import mark_safe
from translate.storage.fluent import (
    FluentPart,
    FluentReference,
    FluentSelectorBranch,
    FluentUnit,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from django.utils.safestring import SafeString

    from weblate.checks.models import Check as CheckModel
    from weblate.trans.models.unit import Unit as TransUnitModel

HighlightsType = list[tuple[int, int, str]]


def translation_from_check(
    check_model: CheckModel,
) -> tuple[TransUnitModel, str, str]:
    """Extract a translation unit, source and target from a Check Model."""
    unit = check_model.unit
    # Do not currently support plurals.
    return (unit, unit.get_source_plurals()[0], unit.get_target_plurals()[0])


def format_html_code(
    format_string: str,
    **kwargs: str,
) -> SafeString:
    """Wrap each keyword argument in a <code> tag."""
    safe_kwargs = {
        key: format_html("<code>{value}</code>", value=value)
        for key, value in kwargs.items()
    }
    if safe_kwargs:
        return format_html(escape(format_string), **safe_kwargs)
    return mark_safe(escape(format_string))  # noqa: S308


def format_html_error_list(errors: Iterable[str]) -> SafeString:
    """Return a HTML SafeString with each given error on a new line."""
    return format_html_join(
        mark_safe("<br />"),
        "{}",
        ((err,) for err in errors),
    )


def variant_name(branches: list[FluentSelectorBranch]) -> str:
    """Get a variant name for the given branch path."""
    if not branches:
        return ""
    return "[" + "][".join(branch.key for branch in branches) + "]"


class FluentPatterns:
    """Patterns from fluent EBNF."""

    BLANK = r"( |\n|\r\n)*"
    # Match string or number literals.
    ESCAPED_CHAR = r'(\\\\|\\"|\\u[0-9a-fA-F]{4}|\\U[0-9a-fA-F]{6})'
    STRING_LITERAL = r'"(' + ESCAPED_CHAR + r'|[^"\\])*"'
    NUMBER_LITERAL = r"-?[0-9]+(\.[0-9]+)?"
    IDENTIFIER = r"[a-zA-Z][a-zA-Z0-9_-]*"
    NAMED_ARGUMENT = (
        IDENTIFIER
        + BLANK
        + r":"
        + BLANK
        + r"("
        + STRING_LITERAL
        + r"|"
        + NUMBER_LITERAL
        + r")"
    )
    NAMED_ARGUMENT_LIST = (
        r"("
        + NAMED_ARGUMENT
        + BLANK
        + r","
        + BLANK
        + r")*"
        + r"("
        + NAMED_ARGUMENT
        + r")?"
    )
    NAMED_ARGUMENTS_CALL = BLANK + r"\(" + BLANK + NAMED_ARGUMENT_LIST + BLANK + r"\)"

    @classmethod
    def placeable(cls, expression: str) -> str:
        """Wrap a fluent expression in placeable."""
        return r"\{" + cls.BLANK + expression + cls.BLANK + r"\}"

    @classmethod
    def reference(cls, ref: FluentReference) -> str:
        """Return a placeable pattern for the given reference."""
        # NOTE: Technically a reference may appear as direct function argument
        # rather than placeables (with the curly braces).  However, we don't
        # expect such references to be common, and they can always include the
        # surrounding braces within the function to achieve the same result.
        # This is most likely to come up for variables. E.g. NUMBER($num).
        # However, it becomes much more difficult to match this expression
        # for highlighting.
        if ref.type_name == "message":
            # Message and message attribute refs do not accept parameters.
            return cls.placeable(re.escape(ref.name))
        if ref.type_name == "term":
            # Term references can accept parameters.
            # NOTE: Technically, positional parameters are allowed by the fluent
            # syntax, which can generally be quite complex expressions. However,
            # a Term would not be able to access this positional information.
            # Instead, we just build the regex to match named arguments, which
            # can only be string or number literals.
            return cls.placeable(
                r"-" + re.escape(ref.name) + r"(" + cls.NAMED_ARGUMENTS_CALL + ")?"
            )
        if ref.type_name == "variable":
            return cls.placeable(r"\$" + re.escape(ref.name))
        return ""

    # Match a completed string or number placeable.
    LITERAL_PLACEABLE_REGEX = re.compile(
        # One or more "{". This should capture cases where the literal is
        # double-wrapped. E.f. { { "literal" } }
        r"(\{"
        + BLANK
        + r")+"
        + r"((?P<string>"
        + STRING_LITERAL
        + ")|(?P<number>"
        + NUMBER_LITERAL
        + r"))"
        # One of more "}".
        # NOTE: In order to be valid Fluent syntax, this should match
        # the same number of opening brackets. We assume the caller is
        # working on such a source with valid Fluent syntax.
        + r"("
        + BLANK
        + r"\})+"
    )

    ESCAPED_CHAR_REGEX = re.compile(ESCAPED_CHAR)

    @classmethod
    def split_literal_expressions(
        cls, source: str
    ) -> Iterator[tuple[int, str, str | None]]:
        """
        Remove all Fluent literal expressions from the given source.

        Returns the non-literal parts of the source as a list of 3-tuples of the
        part's starting offset in the source, its text, and the literal content
        stripped of any surrounding placeholder brackets. The literal content
        will be None for the final entry.
        """
        pos = 0
        for literal_match in cls.LITERAL_PLACEABLE_REGEX.finditer(source):
            string_literal = literal_match.group("string")
            if string_literal is None:
                literal = literal_match.group("number")
            else:
                literal = ""
                for pos, chars in enumerate(
                    # Remove outer quotes from string literal.
                    cls.ESCAPED_CHAR_REGEX.split(string_literal[1:-1])
                ):
                    if not pos % 2:
                        # Not an escaped character.
                        literal += chars
                    elif chars in {'\\"', "\\\\"}:
                        # Unescape the character by removing the "\".
                        literal += chars[1:]
                    else:
                        # Remove the leading "\u" or "\U" and convert hex
                        # sequence to a number.
                        unicode_point = int(chars[2:], 16)  # noqa: FURB166
                        try:
                            # Try unescape the unicode sequence.
                            literal += chr(unicode_point)
                        except ValueError:
                            # Number was too big (and not a valid unicode
                            # character).
                            # Just include the escaped sequence as it was.
                            literal += chars
            yield (
                pos,
                source[pos : literal_match.start()],
                literal,
            )
            pos = literal_match.end()
        yield (pos, source[pos:], None)

    @classmethod
    def highlight_source(
        cls, source: str, highlight_patterns: Iterable[str]
    ) -> HighlightsType:
        """
        Generate a list of highlights for the given source.

        Highlights all matches for the patterns in highlight_patterns, except
        within a literal expression. Returns the highlights as a list of
        3-tuples of the highlighted regions' starting positions, ending
        positions and text.
        """
        unique_highlights = {p for p in highlight_patterns if p}
        if not unique_highlights:
            return []
        regex = re.compile("|".join(unique_highlights), flags=re.MULTILINE)
        highlights: HighlightsType = []
        for start, text, _ in cls.split_literal_expressions(source):
            # NOTE: text may be empty if two literals touch.
            highlights.extend(
                (start + match.start(), start + match.end(), match.group())
                for match in regex.finditer(text)
            )
        return highlights


class FluentUnitConverter:
    """Convert a translation unit into a FluentUnit."""

    def __init__(self, unit: TransUnitModel, source: str) -> None:
        self.unit = unit
        self.source = source

    def fluent_type(self) -> str:
        """Get the fluent type of the given translation unit."""
        flags = self.unit.all_flags
        if flags.has_value("fluent-type"):
            return flags.get_value("fluent-type")
        # Guess based on id.
        if self.unit.context and self.unit.context.startswith("-"):
            return "Term"
        return "Message"

    def to_fluent_unit(self) -> FluentUnit | None:
        """Convert the given translation unit into a FluentUnit."""
        if not self.source:
            return None
        fluent_type = self.fluent_type()
        try:
            return FluentUnit(
                source=self.source, unit_id=self.unit.context, fluent_type=fluent_type
            )
        except ValueError:
            # Unexpected error. E.g. from invalid id.
            # We return a default Message unit instead.
            return FluentUnit(source=self.source)

    def to_fluent_parts(self) -> list[FluentPart] | None:
        """Convert the given translation unit into fluent parts."""
        unit = self.to_fluent_unit()
        if unit is None:
            return None
        return unit.get_parts()

    def get_syntax_error(self) -> str | None:
        """Get the syntax error that would be produced for the unit."""
        unit = self.to_fluent_unit()
        if unit is None:
            return None
        return unit.get_syntax_error()
