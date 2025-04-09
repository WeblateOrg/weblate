# Copyright © Henry Wilkes <henry@torproject.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import html
import re
from typing import TYPE_CHECKING

from django.utils.translation import gettext, gettext_lazy

from weblate.checks.base import SourceCheck, TargetCheck
from weblate.checks.fluent.utils import (
    FluentPatterns,
    FluentUnitConverter,
    format_html_code,
    format_html_error_list,
    translation_from_check,
    variant_name,
)
from weblate.utils.html import format_html_join_comma, list_to_tuples

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from django.utils.safestring import SafeString
    from django_stubs_ext import StrOrPromise
    from translate.storage.fluent import FluentSelectorBranch

    from weblate.checks.fluent.utils import CheckModel, HighlightsType, TransUnitModel

# Standard html elements that do not have content or end tags.
_VOID_ELEMENTS = [
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
]


class _HTMLNode:
    """Represents a found HTML node."""

    def __init__(self, tag: str, parent: _HTMLNode | None) -> None:
        self.parent = parent
        self.children: list[_HTMLNode] = []
        self.tag = tag
        # Keep attributes as a list to keep duplicates.
        self.attributes: dict[str, str] = {}
        if parent:
            parent.children.append(self)

    def descendants(self) -> Iterator[_HTMLNode]:
        """All descendant nodes, not including itself."""
        for child in self.children:
            yield child
            yield from child.descendants()

    def matches(self, other: _HTMLNode) -> bool:
        """Whether the two nodes match."""
        if self.tag != other.tag:
            return False
        if self.attributes != other.attributes:
            return False
        # Two nodes are only match if their ancestors match.
        if self.parent is None:
            return other.parent is None
        if other.parent is None:
            return False
        return self.parent.matches(other.parent)

    def tags(self) -> tuple[str, str]:
        """Get the start and end tags for this node."""
        start = f"<{self.tag}"
        for attr, val in self.attributes.items():
            if '"' in val:
                start += f" {attr}='{val}'"
            else:
                start += f' {attr}="{val}"'
        if self.tag.lower() in _VOID_ELEMENTS:
            start += "/>"
            return (start, "")
        start += ">"
        return (start, f"</{self.tag}>")

    def present(self) -> str:
        """Present this node and all of its ancestors for the user."""
        start = ""
        end = ""

        serialized, end = self.tags()
        if end:
            serialized += "…" + end

        node = self.parent
        while node and node.parent:
            # Also show the parent elements, minus the root.
            start, end = node.tags()
            serialized = start + serialized + end
            node = node.parent

        return serialized


class _HTMLParseError(BaseException):
    """Generic error class for our internal parsing errors."""

    def description(self) -> SafeString:
        raise NotImplementedError


class _HTMLFluentReferenceTagError(_HTMLParseError):
    def __init__(self, sequence: str) -> None:
        self.sequence = sequence

    def description(self) -> SafeString:
        return format_html_code(
            gettext(
                "The Fluent reference in {sequence} may expand into a HTML "
                "tag. Maybe use {suggestion}."
            ),
            sequence=self.sequence,
            suggestion=self.sequence.replace("<", "&lt;", 1),
        )


class _HTMLFluentReferenceCharacterReferenceError(_HTMLParseError):
    def __init__(self, sequence: str) -> None:
        self.sequence = sequence

    def description(self) -> SafeString:
        return format_html_code(
            gettext(
                "The Fluent reference in {sequence} may expand into a HTML "
                "character reference. Maybe use {suggestion}."
            ),
            sequence=self.sequence,
            suggestion=self.sequence.replace("&", "&amp;", 1),
        )


class _HTMLInvalidTagSequenceError(_HTMLParseError):
    """
    Base class for parsing errors in a tag-like sequence.

    We assume the user may not have wanted to create a HTML tag, so we will show
    a suggestion on how to avoid it.
    """

    def __init__(self, sequence: str) -> None:
        self.sequence = sequence

    @property
    def suggestion(self) -> str:
        return self.sequence.replace("<", "&lt;", 1)


class _HTMLInvalidEndTagError(_HTMLInvalidTagSequenceError):
    def description(self) -> SafeString:
        return format_html_code(
            gettext(
                "The sequence {sequence} begins with a HTML closing tag, "
                "but the name or syntax is not valid. "
                "If you do not want a closing tag, use {suggestion}."
            ),
            sequence=self.sequence,
            suggestion=self.suggestion,
        )


class _HTMLInvalidStartTagNameError(_HTMLInvalidTagSequenceError):
    def description(self) -> SafeString:
        return format_html_code(
            gettext(
                "The sequence {sequence} begins with a HTML tag, "
                "but the name is not valid. "
                "If you do not want to begin a HTML tag, use {suggestion}."
            ),
            sequence=self.sequence,
            suggestion=self.suggestion,
        )


class _HTMLStartTagNotClosedError(_HTMLInvalidTagSequenceError):
    def description(self) -> SafeString:
        return format_html_code(
            gettext(
                "The sequence {sequence} begins with a HTML tag, "
                "but the tag is never closed by {close}. "
                "If you do not want to begin a HTML tag, use {suggestion}."
            ),
            sequence=self.sequence,
            close=">",
            suggestion=self.suggestion,
        )


class _HTMLTagTypeNotAllowedError(_HTMLInvalidTagSequenceError):
    def description(self) -> SafeString:
        return format_html_code(
            gettext(
                "Fluent inner HTML should not include {sequence}. "
                "Maybe use {suggestion}."
            ),
            sequence=self.sequence,
            suggestion=self.suggestion,
        )


class _HTMLUnexpectedAttributeError(_HTMLInvalidTagSequenceError):
    def __init__(self, tag: str, attribute: str) -> None:
        super().__init__(tag)
        self.attribute = attribute

    def description(self) -> SafeString:
        return format_html_code(
            gettext(
                "The sequence {sequence} begins with a HTML tag, "
                "but the sequence {attribute} is not a valid attribute "
                "with a value. "
                "If you do not want to begin a HTML tag, use {suggestion}."
            ),
            sequence=self.sequence,
            attribute=self.attribute,
            suggestion=self.suggestion,
        )


class _HTMLInvalidAttributeNameError(_HTMLParseError):
    def __init__(self, tag: str, name: str) -> None:
        self.tag = tag
        self.name = name

    def description(self) -> SafeString:
        return format_html_code(
            gettext("The HTML attribute name {name} for the {tag} tag is not valid."),
            name=self.name,
            tag=f"<{self.tag}>",
        )


class _HTMLInvalidAttributeValueError(_HTMLParseError):
    def __init__(self, tag: str, name: str, value: str) -> None:
        self.tag = tag
        self.name = name
        self.value = value

    def description(self) -> SafeString:
        return format_html_code(
            gettext(
                "The HTML {name} attribute value {value} for the {tag} "
                "tag is not a valid quoted value."
            ),
            name=self.name,
            value=self.value,
            tag=f"<{self.tag}>",
        )


class _HTMLDuplicateAttributeNameError(_HTMLParseError):
    def __init__(self, tag: str, name: str) -> None:
        self.tag = tag
        self.name = name

    def description(self) -> SafeString:
        return format_html_code(
            gettext("The HTML {name} attribute appears twice for the {tag} tag."),
            name=self.name,
            tag=f"<{self.tag}>",
        )


class _HTMLUnmatchedEndTagError(_HTMLParseError):
    def __init__(self, tag: str) -> None:
        self.tag = tag

    def description(self) -> SafeString:
        return format_html_code(
            gettext("Unmatched HTML end tag: {tag}."), tag=f"</{self.tag}>"
        )


class _HTMLVoidEndTagError(_HTMLParseError):
    def __init__(self, tag: str) -> None:
        self.tag = tag

    def description(self) -> SafeString:
        return format_html_code(
            gettext("The HTML {name} void element should not have an end tag: {end}."),
            name=self.tag,
            end=f"</{self.tag}>",
        )


class _HTMLNonVoidSelfClosedError(_HTMLParseError):
    def __init__(self, tag: str) -> None:
        self.tag = tag

    def description(self) -> SafeString:
        return format_html_code(
            gettext(
                "The HTML {name} element is not a known void element, so "
                "should not have a self-closing tag: {self_close}."
            ),
            name=self.tag,
            self_close=f"<{self.tag}/>",
        )


class _HTMLMissingEndTagError(_HTMLParseError):
    def __init__(self, tag: str) -> None:
        self.tag = tag

    def description(self) -> SafeString:
        return format_html_code(
            gettext("The HTML {tag} tag is missing a matching end tag: {end}."),
            tag=f"<{self.tag}>",
            end=f"</{self.tag}>",
        )


class _HTMLUnexpectedCharacterReferenceError(_HTMLParseError):
    def __init__(self, sequence: str) -> None:
        self.sequence = sequence

    def description(self) -> SafeString:
        # We primarily assume the user did not intend to create a character
        # reference.
        suggestion = self.sequence.replace("&", "&amp;", 1)
        return format_html_code(
            gettext(
                "The sequence {sequence} will begin a HTML character "
                "reference, but does not end with {semicolon}. "
                "If you do not want a character reference, use {suggestion}."
            ),
            sequence=self.sequence,
            semicolon=";",
            suggestion=suggestion,
        )


class _HTMLInvalidCharacterReferenceError(_HTMLParseError):
    def __init__(self, sequence: str) -> None:
        self.sequence = sequence

    def description(self) -> SafeString:
        # We primarily assume the user did not intend to create a character
        # reference.
        return format_html_code(
            gettext("The sequence {sequence} is not a valid HTML character reference."),
            sequence=self.sequence,
        )


class _HTMLSourcePosition:
    """Keeps track of some source string and a position in that string."""

    def __init__(self, serialized: str) -> None:
        self.pos = 0
        self.source = ""
        self._start_end_literals: list[tuple[int, int]] = []

        # Since FluentPatternVariants correspond to flat Patterns, we
        # don't expect any SelectExpressions, but it might contain other
        # "flat" references. E.g.
        #   contact { $person } at { 123 }
        #
        # We need this to be valid HTML *after* expanding the literals.
        for _pos, text, literal in FluentPatterns.split_literal_expressions(serialized):
            self.source += text
            if literal:
                start = len(self.source)
                self._start_end_literals.append((start, start + len(literal)))
                self.source += literal

    def reset(self) -> None:
        """Reset the position back to the start."""
        self.pos = 0

    def at_literal(self) -> bool:
        """Whether the current position is within a Fluent literal or not."""
        return any(
            self.pos >= start and self.pos < end
            for start, end in self._start_end_literals
        )

    def match(self, regex: re.Pattern) -> re.Match | None:
        """
        Try and match with the given regular expression.

        The match is performed at the current source position.

        If the expressions match, the source position will automatically move
        forward to the end of the match.
        """
        match = regex.match(self.source, self.pos)
        if not match:
            return None
        self.pos = match.end()
        return match

    def get(self, regex: re.Pattern) -> str:
        """
        Get the matched text for the given regular expression.

        The text is fetched from the current source position, without changing
        its value.

        If nothing is matched, then an empty string is returned.
        """
        match = regex.match(self.source, self.pos)
        if not match:
            return ""
        return match.group()

    def peak_matches(self, regex: re.Pattern) -> bool:
        """
        Peak whether the we match with the given regular expression.

        The match is performed at the current source position.

        If there is a match, this will return True without changing the source
        position. Otherwise it will return False.
        """
        return regex.match(self.source, self.pos) is not None


class _CountedNodes:
    """
    Tracks the number of matching _HTMLNodes in a list.

    This will collect matching nodes together so they can be counted and
    compared, without caring about the order.
    """

    def __init__(self, node_list: Iterable[_HTMLNode]) -> None:
        # Each entry in matching_nodes is a list of nodes that all match. The
        # length of this list is the count.
        self.matching_nodes: list[list[_HTMLNode]] = []
        for node in node_list:
            add = True
            for other_nodes in self.matching_nodes:
                if other_nodes[0].matches(node):
                    add = False
                    other_nodes.append(node)
                    break
            if add:
                self.matching_nodes.append([node])

    def matches(self, other: _CountedNodes) -> bool:
        """
        Whether the two instances match.

        This will match if the two instances have matching _HTMLNodes with the
        same count in both.
        """
        if len(self.matching_nodes) != len(other.matching_nodes):
            return False
        for nodes in self.matching_nodes:
            has_match = False
            for _index, other_nodes in enumerate(other.matching_nodes):
                if nodes[0].matches(other_nodes[0]):
                    if len(nodes) != len(other_nodes):
                        return False
                    has_match = True
                    break
            if not has_match:
                return False
        # Both are the same length and each node in self was matched, so there
        # shouldn't be any nodes in other that were not matched once.
        return True

    def count(self, node: _HTMLNode) -> int:
        """Count how many nodes match the given node."""
        for other_nodes in self.matching_nodes:
            if node.matches(other_nodes[0]):
                return len(other_nodes)
        return 0


class _VariantNodes:
    """Represents a variant string and the _HTMLNodes it contains."""

    def __init__(
        self,
        path: list[FluentSelectorBranch],
        root: _HTMLNode,
    ) -> None:
        self.path = path
        self.root = root
        self._nodes: list[_HTMLNode] | None = None
        self._counted_nodes: _CountedNodes | None = None

    @property
    def nodes(self) -> list[_HTMLNode]:
        """The nodes found in this variant."""
        if self._nodes is None:
            self._nodes = list(self.root.descendants())
        return self._nodes

    @property
    def counted_nodes(self) -> _CountedNodes:
        """The nodes found in this variant, grouped with matching nodes."""
        if self._counted_nodes is None:
            self._counted_nodes = _CountedNodes(self.nodes)
        return self._counted_nodes

    def name(self) -> str:
        """Generate name for this variant."""
        return variant_name(self.path)


class _FluentInnerHTMLCheck:
    """
    Check that we have valid inner HTML.

    This will check that the given translation unit's source or target has inner
    HTML that will not lead to a loss of content when parsed.
    """

    # Pattern to search for the next tag.
    _NEXT_TAG_REGEX = re.compile(r"[^<]*<")
    # Pattern that starts an end-tag.
    _OPEN_END_TAG_REGEX = re.compile(r"\/")

    # Do not allow processing instructions, or comments or CDATA or DOCTYPE.
    _TAG_NOT_ALLOWED_FIRST_CHAR_REGEX = re.compile(r"[!?]")

    # First character of tag must be ASCII alpha, as per HTML spec. Unlike the
    # spec, we also restrict the other characters to be ASCII alphanumeric or
    # "-".
    _TAG_FIRST_CHAR = r"[a-zA-Z]"
    _TAG_FIRST_CHAR_REGEX = re.compile(_TAG_FIRST_CHAR)
    _TAG_PATTERN = _TAG_FIRST_CHAR + r"[a-zA-Z0-9-]*"

    # Only allow a limited set of "blank" characters within a tag.
    _BLANK_CHAR = r"[ \t\n]"
    # Match either the closing of a start-tag, or some whitespace, or the end of
    # the string.
    _CLOSE_BLANK_OR_END_PATTERN = (
        r"("
        + (_BLANK_CHAR + r"*(?P<close>\/?>)")  # Blanks followed by ">" or "/>",
        + r"|"  # or
        + (_BLANK_CHAR + r"*(?P<eof>$)")  # end of the string,
        + r"|"  # or
        + (_BLANK_CHAR + r"+")  # a required blank.
        # NOTE: The <eof> group will match before the blank group. E.g. "   x"
        # will match blank, but "   " will match <eof>.
        + r")"
    )
    _START_TAG_REGEX = re.compile(
        r"(?P<tag>" + _TAG_PATTERN + r")" + _CLOSE_BLANK_OR_END_PATTERN
    )
    # Only allow a limited set of characters for attribute names, which should
    # cover HTML attributes and "data-" attributes.
    # Also require ending with an "=".
    _ATTRIBUTE_NAME_PATTERN = r"(?P<name>[a-zA-Z][a-zA-Z0-9_.:-]*)="
    # Only allow quoted values.
    # NOTE: We do not use a raw string since we want the '\"' to become a
    # literal '"'.
    _ATTRIBUTE_VALUE_PATTERN = "('(?P<value1>[^']*)'|\"(?P<value2>[^\"]*)\")"
    _ATTRIBUTE_NAME_REGEX = re.compile(_ATTRIBUTE_NAME_PATTERN)
    _ATTRIBUTE_VALUE_REGEX = re.compile(
        _ATTRIBUTE_VALUE_PATTERN
        # Followed by a blank or the closing character.
        + _CLOSE_BLANK_OR_END_PATTERN
    )
    _END_TAG_REGEX = re.compile(r"(?P<tag>" + _TAG_PATTERN + r")" + _BLANK_CHAR + r"*>")

    # Pattern used to pull text within a suspected tag up until the next
    # attribute or the tag closes.
    _NON_BLANK_OR_CLOSE_REGEX = re.compile(r"[^ \t\n>]*")

    _FLUENT_REF_FIRST_CHAR_REGEX = re.compile(r"\{")
    # This pattern will match basic fluent references, but will break down for
    # references that contain sub-placeables or "}" literals. However, we only
    # use this for warning messages, so it is good enough.
    # Similarly we make the last "}" optional, even though this would indicate
    # invalid Fluent syntax, but we want a guaranteed match if we already match
    _FLUENT_REF_REGEX = re.compile(r"\{[^}]*\}?")

    # For highlighting tags.
    ALL_TAGS_REGEX = re.compile(
        # Start tag.
        r"<"
        + _TAG_PATTERN
        # Attributes.
        + r"("
        + (_BLANK_CHAR + r"+" + _ATTRIBUTE_NAME_PATTERN + _ATTRIBUTE_VALUE_PATTERN)
        + r")*"
        # Close start tag.
        + (_BLANK_CHAR + r"*\/?>")
        + r"|"
        # End tag.
        + (r"<\/" + _TAG_PATTERN + _BLANK_CHAR + r"*>")
    )

    @classmethod
    def _non_blank_or_close(cls, source: _HTMLSourcePosition) -> str:
        """
        Get all the non-blank and non ">" characters found at the start.

        This is used to grab some joined sequence of characters within a HTML
        tag to show back to the user.
        """
        return source.get(cls._NON_BLANK_OR_CLOSE_REGEX)

    @classmethod
    def _parse_end_tag(
        cls, source: _HTMLSourcePosition, open_nodes: list[_HTMLNode]
    ) -> None:
        """Parse an end tag, starting after the "</"."""
        end_tag_match = source.match(cls._END_TAG_REGEX)
        if not end_tag_match:
            # May correspond to using a non-ASCII alphanumeric value in the tag
            # name, which whilst technically allowed for HTML, is not allowed by
            # this check.
            #
            # Otherwise, this is expected to correspond to some HTML parsing
            # error, like:
            # + invalid-first-character-of-tag-name
            # + eof-in-tag
            # + end-tag-with-attributes
            # + missing-end-tag-name
            #
            # In which cases some content will be *lost* when parsed as HTML by
            # being commented out or ignored.
            #
            # Some parsing errors, like eof-before-tag-name, will not lead to a
            # loss of content, but aren't allowed here for consistency.
            raise _HTMLInvalidEndTagError("</" + cls._non_blank_or_close(source))

        tag = end_tag_match.group("tag")

        if tag.lower() in _VOID_ELEMENTS:
            raise _HTMLVoidEndTagError(tag)

        node = open_nodes.pop()
        # Never close our dummy "root" element. So raise error if open_nodes is
        # now empty.
        if not open_nodes or node.tag != tag:
            raise _HTMLUnmatchedEndTagError(tag)

    @classmethod
    def _parse_attribute(
        cls,
        source: _HTMLSourcePosition,
        node: _HTMLNode,
    ) -> re.Match:
        """Parse a start tag attribute, starting at the attribute name."""
        name_match = source.match(cls._ATTRIBUTE_NAME_REGEX)
        if not name_match:
            non_blank = cls._non_blank_or_close(source)
            if "=" not in non_blank:
                # Doesn't look like an attribute with a value.
                raise _HTMLUnexpectedAttributeError("<" + node.tag, non_blank)
            raise _HTMLInvalidAttributeNameError(
                node.tag,
                non_blank[: non_blank.index("=")],
            )

        name = name_match.group("name")
        if name in node.attributes:
            raise _HTMLDuplicateAttributeNameError(node.tag, name)
        value_match = source.match(cls._ATTRIBUTE_VALUE_REGEX)
        if not value_match:
            raise _HTMLInvalidAttributeValueError(
                node.tag, name, cls._non_blank_or_close(source)
            )

        value = value_match.group("value1")
        if value is None:
            value = value_match.group("value2")

        node.attributes[name] = value

        return value_match

    @classmethod
    def _parse_start_tag(
        cls, source: _HTMLSourcePosition, open_nodes: list[_HTMLNode]
    ) -> None:
        """Parse a start tag, starting after the opening "<"."""
        if (
            # If we are pointing to a literal character, then this "{" should
            # not be part of a fluent reference, but be a literal "{" instead.
            not source.at_literal()
            and source.peak_matches(cls._FLUENT_REF_FIRST_CHAR_REGEX)
        ):
            # Starts a Fluent reference. E.g.
            #   contact <{ $name }
            # If the "$name" starts with an ASCII alpha it could expand to
            # a tag.
            #
            # NOTE: This won't capture all cases where the reference might
            # expand into some HTML, but generally we expect the fluent
            # application to ensure their references are sanitized for
            # inner HTML. But this seems like a case where a sanitized value
            # might become unintentionally bad.
            #
            # NOTE: If the fluent reference appears elsewhere within the tag
            # it will be invalid (not a valid tag name or attribute name) except
            # within a quoted attribute value. A quoted attribute value can
            # still cause problems when it is expanded with the value. E.g. if
            # the value closes the quotes and injects parts, but we are not
            # trying to protect against this.
            raise _HTMLFluentReferenceTagError("<" + source.get(cls._FLUENT_REF_REGEX))

        tag_not_allowed_match = source.match(cls._TAG_NOT_ALLOWED_FIRST_CHAR_REGEX)
        if tag_not_allowed_match:
            raise _HTMLTagTypeNotAllowedError("<" + tag_not_allowed_match.group())

        if not source.peak_matches(cls._TAG_FIRST_CHAR_REGEX):
            # Corresponds to the HTML parsing errors
            # + invalid-first-character-of-tag-name, and
            # + eof-before-tag-name
            # for a start tag, so the "<" will be treated as text content.
            # So can keep this "<" character and move on.
            return

        tag_match = source.match(cls._START_TAG_REGEX)
        if not tag_match:
            raise _HTMLInvalidStartTagNameError("<" + cls._non_blank_or_close(source))

        tag = tag_match.group("tag")

        node = _HTMLNode(tag, open_nodes[-1])

        end_match = tag_match
        while True:
            closing_part = end_match.group("close")
            if closing_part is not None:
                # Void element has no content, so is not added to the list
                # of open_nodes. Being self-closing is optional.
                if tag.lower() not in _VOID_ELEMENTS:
                    # Non-void elements should not be self-closing.
                    if closing_part == "/>":
                        raise _HTMLNonVoidSelfClosedError(tag)
                    open_nodes.append(node)
                return

            if end_match.group("eof") is not None:
                # Corresponds to HTML parsing error eof-in-tag.
                # We have some blank, but then reach the end of the string
                # before the tag is closed.
                raise _HTMLStartTagNotClosedError("<" + tag)

            end_match = cls._parse_attribute(source, node)

    # Check for:
    # + valid character refs (like "&lt;", "&frac12;", "&#80;" or "&#x80"), or
    # + character refs that may expand in some way, but likely were not intended
    #   by the user because they are missing the ";" (like "&ethical"), or
    # + sequences that look like character refs that the user wants to expand
    #   (because they are alphanumeric and end with ";"), but may not actually
    #   expand as expected.
    _CHARACTER_REFS_REGEX = re.compile(r"[^&]*(?P<ref>&#?[a-zA-Z0-9]*;?)")

    @classmethod
    def _check_character_refs(cls, source: _HTMLSourcePosition) -> None:
        """
        Check that the character references found in the source.

        A character reference must be either intentional (with a semicolon) and
        valid, or unintentional but will not expand into a reference under the
        HTML spec, so are safe to keep in HTML.
        """
        # NOTE: The HTML5 spec (13.2.5.73 Named character reference state), for
        # historical reasons, will treat character references that do not end
        # with a ";", but are followed by an alphanumeric or "=", differently
        # depending on whether we are in text content or an attribute value.
        # E.g. "&ltx" will become "<x" for text content but will remain as
        # "&ltx" for an attribute value.
        # Even though "&ltx" will not expand for an attribute, we still want to
        # raise an error against it for consistency. So we treat this the same
        # as text content.
        while True:
            # Will always match at least "&" if it exists.
            ref_match = source.match(cls._CHARACTER_REFS_REGEX)
            if not ref_match:
                return

            sequence = ref_match.group("ref")
            closes_with_semicolon = sequence[-1] == ";"

            if (
                not closes_with_semicolon
                # If we are pointing to a literal character, then this "{"
                # should not be part of a fluent reference, but be a literal "{"
                # instead, which will break the HTML character reference.
                and not source.at_literal()
                # Next character is "{".
                and source.peak_matches(cls._FLUENT_REF_FIRST_CHAR_REGEX)
            ):
                # Could expand to a character reference when the fluent
                # reference is substituted. E.g.
                #   &l{ $var }
                # or
                #   &#{ $var }
                raise _HTMLFluentReferenceCharacterReferenceError(
                    sequence + source.get(cls._FLUENT_REF_REGEX)
                )

            expanded = html.unescape(sequence)
            if not closes_with_semicolon and expanded != sequence:
                # Roughly corresponds to the parse error
                # missing-semicolon-after-character-reference
                # We treat this as an unintended expansion on the user's part.
                raise _HTMLUnexpectedCharacterReferenceError(sequence)
            if closes_with_semicolon and expanded[-1] == ";":
                # Failed to expand at all (e.g. for the parse error
                # unknown-named-character-reference), or expanded earlier than
                # the intended ";".
                #
                # We treat this as the user trying to do an expansion that
                # fails.
                raise _HTMLInvalidCharacterReferenceError(sequence)

    @classmethod
    def _parse_basic_inner_html(cls, serialized: str) -> _HTMLNode:
        """
        Parse the given source as basic inner HTML.

        Returns the list of all nodes found.
        """
        source = _HTMLSourcePosition(serialized)

        cls._check_character_refs(source)
        source.reset()

        open_nodes = [_HTMLNode("root", None)]
        while True:
            # We start in the HTML "data state", this can end with:
            # + "&" which enters the "character reference state", we check this
            #   in _check_character_refs.
            # + "<" which enters the "tag open state".
            #
            # NOTE: This skips past any ">" characters. We expect these
            # characters to be handled ok for innerHTML.
            open_tag_match = source.match(cls._NEXT_TAG_REGEX)
            if open_tag_match is None:
                break

            if source.match(cls._OPEN_END_TAG_REGEX):
                cls._parse_end_tag(source, open_nodes)
            else:
                cls._parse_start_tag(source, open_nodes)

        if len(open_nodes) > 1:
            raise _HTMLMissingEndTagError(open_nodes[1].tag)

        return open_nodes[0]

    @classmethod
    def get_fluent_inner_html(
        cls,
        unit: TransUnitModel,
        unit_source: str,
    ) -> list[_VariantNodes] | None:
        """
        Get the list of HTML nodes found in each variant.

        Returns None if there is a syntax error or no value.
        """
        unit_parts = FluentUnitConverter(unit, unit_source).to_fluent_parts()
        if unit_parts is None:
            return None
        for part in unit_parts:
            if not part.name:
                # We only want to process the Fluent value part as HTML since
                # the attributes will not likely become inner HTML.
                return [
                    _VariantNodes(
                        path,
                        cls._parse_basic_inner_html(
                            part.top_branch.to_flat_string(path)
                        ),
                    )
                    for path in part.top_branch.branch_paths()
                ]
        # No value part.
        return None


class FluentSourceInnerHTMLCheck(_FluentInnerHTMLCheck, SourceCheck):
    """
    Check that the source value works as inner HTML.

    Fluent is often used in contexts where the value for a Message (or Term) is
    meant to be used directly as ``.innerHTML`` (rather than ``.textContent``)
    for some HTML element. For example, when using the Fluent DOM package.

    The aim of this check is to predict how the value will be parsed as inner
    HTML, assuming a HTML5 conforming parser, to catch cases where there would
    be some "unintended" loss of the string, without being too strict about
    technical parsing errors that do *not* lead to a loss of the string.

    This check is applied to the value of Fluent Messages or Terms, but not
    their Attributes. For Messages, the Fluent Attributes are often just HTML
    attribute values, so can be arbitrary strings. For Terms, the Fluent
    Attributes are often language properties that can only be referenced in the
    selectors of Fluent Select Expressions.

    Generally, most Fluent values are not expected to contain any HTML markup.
    Therefore, this check does not expect or want translators and developers to
    have to care about strictly avoiding *any* technical HTML5 parsing errors
    (let alone XHTML parsing errors). Instead, this check will just want to warn
    them when they may have unintentionally opened a HTML tag or inserted a
    character reference.

    Moreover, for the Fluent values that intentionally contain HTML tags or
    character references, this check will verify some "good practices", such as
    matching closing and ending tags, valid character references, and quoted
    attribute values. In addition, whilst the HTML5 specification technically
    allows for quite arbitrary tag and attribute names, this check will restrain
    them to some basic ASCII values that should cover the standard HTML5 element
    tags and attributes, as well as allow *some* custom element or attribute
    names. This is partially to ensure that the user is using HTML
    intentionally.

    NOTE: This check will *not* ensure the inner HTML is safe or sanitized, and
    is not meant to protect against malicious attempts to alter the inner HTML.
    Moreover, it should be remembered that Fluent variables and references may
    expand to arbitrary strings, so could expand to arbitrary HTML unless they
    are escaped. As an exception, a ``<`` or ``&`` character before a Fluent
    reference will trigger this check since even an escaped value could lead to
    unexpected results.

    NOTE: The Fluent DOM package has further limitations, such as allowed tags
    and attributes, which this check will not enforce.
    """

    check_id = "fluent-source-inner-html"
    name = gettext_lazy("Fluent source inner HTML")
    description = gettext_lazy("Fluent source should be valid inner HTML.")
    default_disabled = True

    def check_source_unit(self, sources: list[str], unit: TransUnitModel) -> bool:
        try:
            self.get_fluent_inner_html(unit, sources[0])
        except _HTMLParseError:
            return True
        return False

    def get_description(self, check_model: CheckModel) -> StrOrPromise:
        unit, source, _target = translation_from_check(check_model)
        try:
            self.get_fluent_inner_html(unit, source)
        except _HTMLParseError as err:
            return err.description()
        return super().get_description(check_model)


class _VariantNodesDifference:
    """
    The difference between the nodes found in the source and target.

    Each variant in the source will be compared against each variant in the
    target to see if they have a matching set of nodes with the same number or
    appearances, but not necessarily in the same order.

    If there is any source variant that does not have at least one match in the
    target, it will be flagged as a missing variant. Similarly, if there is any
    target variant with no matching source variant, it will be flagged as an
    extra variant.
    """

    def __init__(
        self,
        source_variant_nodes: list[_VariantNodes],
        target_variant_nodes: list[_VariantNodes],
    ) -> None:
        self._source_variants = source_variant_nodes
        self._target_variants = target_variant_nodes

        self._missing_variants = [
            variant
            for variant in self._source_variants
            if not self._has_match(variant, self._target_variants)
        ]
        self._extra_variants = [
            variant
            for variant in self._target_variants
            if not self._has_match(variant, self._source_variants)
        ]

    @staticmethod
    def _has_match(
        variant: _VariantNodes,
        search_list: list[_VariantNodes],
    ) -> bool:
        return any(
            variant.counted_nodes.matches(other.counted_nodes) for other in search_list
        )

    def __bool__(self) -> bool:
        return bool(self._missing_variants or self._extra_variants)

    @staticmethod
    def _missing_element_message(
        tag: str,
        variants: str,
    ) -> SafeString:
        if not variants:
            return format_html_code(
                gettext("Fluent value is missing a HTML {tag} tag."),
                tag=tag,
            )
        return format_html_code(
            gettext(
                "Fluent value is missing a HTML {tag} tag "
                "for the following variants: {variant_list}."
            ),
            tag=tag,
            variant_list=variants,
        )

    @staticmethod
    def _extra_element_message(
        tag: str,
        variants: str,
    ) -> SafeString:
        if not variants:
            return format_html_code(
                gettext("Fluent value has an unexpected extra HTML {tag} tag."),
                tag=tag,
            )
        return format_html_code(
            gettext(
                "Fluent value has an unexpected extra HTML {tag} tag "
                "for the following variants: {variant_list}."
            ),
            tag=tag,
            variant_list=variants,
        )

    @staticmethod
    def _present_variant_list(
        variant_list: list[_VariantNodes] | None,
    ) -> str:
        if not variant_list:
            return ""
        return format_html_join_comma(
            "{}", list_to_tuples(variant.name() for variant in variant_list)
        )

    def _unique_target_nodes(self) -> Iterator[_HTMLNode]:
        unique_nodes: list[_HTMLNode] = []
        for variant in self._target_variants:
            for node in variant.nodes:
                add = True
                for other in unique_nodes:
                    if other.matches(node):
                        add = False
                        break
                if add:
                    unique_nodes.append(node)
                    yield node

    def _errors_relative_to(
        self,
        source_counted_nodes: _CountedNodes,
    ) -> Iterator[SafeString]:
        for nodes in source_counted_nodes.matching_nodes:
            count = len(nodes)
            variants_missing_node = []
            all_variants = True
            for variant in self._target_variants:
                if variant.counted_nodes.count(nodes[0]) < count:
                    variants_missing_node.append(variant)
                else:
                    all_variants = False
            if not variants_missing_node:
                continue
            yield self._missing_element_message(
                nodes[0].present(),
                self._present_variant_list(
                    None if all_variants else variants_missing_node
                ),
            )

        for node in self._unique_target_nodes():
            count = source_counted_nodes.count(node)
            variants_extra_node = []
            all_variants = True
            for variant in self._target_variants:
                if variant.counted_nodes.count(node) > count:
                    variants_extra_node.append(variant)
                else:
                    all_variants = False
            if not variants_extra_node:
                continue
            yield self._extra_element_message(
                node.present(),
                self._present_variant_list(
                    None if all_variants else variants_extra_node
                ),
            )

    def _missing_variants_message(
        self,
        variants: list[_VariantNodes],
    ) -> SafeString:
        # NOTE: variants should all have names since the source contains at
        # least two variants in order to reach this step.
        variant_list = self._present_variant_list(variants)
        return format_html_code(
            gettext(
                "The following variants in the original Fluent value do not "
                "have at least one matching variant in the translation with "
                "the same set of HTML elements: {variant_list}."
            ),
            variant_list=variant_list,
        )

    def _extra_variants_message(
        self,
        variants: list[_VariantNodes] | None,
    ) -> SafeString:
        variant_list = self._present_variant_list(variants)
        if not variant_list:
            return format_html_code(
                gettext(
                    "The translated Fluent value does not "
                    "have a matching variant in the original with the same "
                    "set of HTML elements."
                ),
            )
        return format_html_code(
            gettext(
                "The following variants in the translated Fluent "
                "value do not have a matching variant in "
                "the original with the same set of HTML elements: "
                "{variant_list}."
            ),
            variant_list=variant_list,
        )

    def _errors_for_unmatched_variants(
        self,
    ) -> Iterator[SafeString]:
        if self._missing_variants:
            yield self._missing_variants_message(self._missing_variants)
        if self._extra_variants:
            # Don't want to print a list of variants if we only have one in the
            # original.
            have_target_variants = len(self._target_variants) > 1
            yield self._extra_variants_message(
                self._extra_variants if have_target_variants else None
            )

    def description(self) -> SafeString:
        """Generate a description of the differences between the source and target."""
        # We want to be able to compare each target variant against some common
        # set of expected nodes. This allows us to determine which specific
        # nodes are missing or extra.
        # This is only possible if each variant in the source has the same set
        # of nodes to allow for this one-to-one comparison. But we expect this
        # will happen in most cases.
        common_nodes: _CountedNodes | None = None
        for variant in self._source_variants:
            if common_nodes is None:
                common_nodes = variant.counted_nodes
            elif not common_nodes.matches(variant.counted_nodes):
                common_nodes = None
                break

        if common_nodes is not None:
            return format_html_error_list(self._errors_relative_to(common_nodes))
        # The source contains multiple variants with different node counts.
        return format_html_error_list(self._errors_for_unmatched_variants())


class FluentTargetInnerHTMLCheck(_FluentInnerHTMLCheck, TargetCheck):
    """
    Check that the target value has the same HTML nodes as the source.

    This check will verify that the translated value of a Message or Term
    contains the same HTML elements as the source value.

    First, if the source value fails the `check-fluent-source-inner-html` check,
    then this check will do nothing. Otherwise, the translated value will also
    be checked under the same conditions.

    Second, the HTML elements found in the translated value will be compared
    against the HTML elements found in the source value. Two elements will match
    if they share the exact same tag name, the exact same attributes and values,
    and all their ancestors match in the same way. This check will ensure that
    all the elements in the source appear somewhere in the translation, with the
    same *number* of appearances, and with no additional elements added. When
    there are multiple elements in the value, they need not appear in the same
    order in the translation value.

    When the source or translation contains Fluent Select Expressions, then each
    possible variant in the source must be matched with at least one variant in
    the translation with the same HTML elements, and vice versa.

    When using Fluent in combination with the Fluent DOM package, this check
    will ensure that the translation also includes any required
    ``data-l10n-name`` elements that appear in the source, or any of the allowed
    inline elements like ``<br>``.
    """

    # E.g. if the source is
    #
    # m = You <em>must</em> visit <a data-l10n-name="link">my homepage</a>
    #
    # Then we would expect the translation to include the <em> element and the
    # <a> element *including* the same "data-l10n-name" attribute and value.

    check_id = "fluent-target-inner-html"
    name = gettext_lazy("Fluent translation inner HTML")
    description = gettext_lazy("Fluent target should be valid inner HTML that matches.")
    default_disabled = True

    @classmethod
    def _compare_inner_html(
        cls, unit: TransUnitModel, source: str, target: str
    ) -> _VariantNodesDifference | None:
        # May raise a _HTMLParseError.
        target_variant_nodes = cls.get_fluent_inner_html(unit, target)

        try:
            source_variant_nodes = cls.get_fluent_inner_html(unit, source)
        except _HTMLParseError:
            # If the source is invalid, we do not expect the target to match.
            return None

        if source_variant_nodes is None:
            # Invalid syntax or no value, leave this to the syntax check and
            # part check.
            return None

        if target_variant_nodes is None:
            # Invalid syntax or no value in target. Leave this to the syntax
            # check and part check.
            return None

        # Compare every variant in the target against every variant in the
        # source. Each variant's list of nodes should match at least one other
        # variant's list of nodes.
        return _VariantNodesDifference(
            source_variant_nodes,
            target_variant_nodes,
        )

    def check_single(
        self,
        source: str,
        target: str,
        unit: TransUnitModel,
    ) -> bool:
        try:
            difference = self._compare_inner_html(unit, source, target)
        except _HTMLParseError:
            return True
        return bool(difference)

    def get_description(self, check_model: CheckModel) -> StrOrPromise:
        unit, source, target = translation_from_check(check_model)
        try:
            difference = self._compare_inner_html(unit, source, target)
        except _HTMLParseError as err:
            return err.description()

        if not difference:
            return super().get_description(check_model)

        return difference.description()

    def check_highlight(
        self,
        source: str,
        unit: TransUnitModel,
    ) -> HighlightsType:
        if self.should_skip(unit):
            return []

        # We simply highlight all HTML tags that are valid tags according to our
        # parser, regardless of whether it matches a tag found in the source.
        return [
            (match.start(), match.end(), match.group())
            for match in self.ALL_TAGS_REGEX.finditer(source)
        ]
