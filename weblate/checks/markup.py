# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from collections import Counter, defaultdict
from functools import cache, lru_cache
from itertools import chain
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils.functional import cached_property
from django.utils.html import format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, gettext_lazy
from docutils import utils
from docutils.core import Publisher
from docutils.nodes import Element, system_message

from weblate.checks.base import MissingExtraDict, TargetCheck
from weblate.utils.html import (
    MD_BROKEN_LINK,
    MD_LINK,
    MD_REFLINK,
    MD_SYNTAX,
    MD_SYNTAX_GROUPS,
    HTMLSanitizer,
)
from weblate.utils.xml import parse_xml

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise
    from lxml.etree import _Element

    from weblate.trans.models import Unit

    from .models import Check

BBCODE_MATCH = re.compile(
    r"(?P<start>\[(?P<tag>[^]]+)(@[^]]*)?\])(.*?)(?P<end>\[\/(?P=tag)\])", re.MULTILINE
)


XML_MATCH = re.compile(r"<[^>]+>")
XML_ENTITY_MATCH = re.compile(
    r"""
    # Initial &
    \&
        (
            # CharRef
            \x23[0-9]+
        |
            # CharRef
			\x23x[0-9a-fA-F]+
        |
            # EntityRef
            # NameStartChar
            [:A-Z_a-z\xC0-\xD6\xD8-\xF6\xF8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\u10000-\uEFFFF]
            # NameChar
            [0-9\xB7.:A-Z_a-z\xC0-\xD6\xD8-\xF6\xF8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\u10000-\uEFFFF\u0300-\u036F\u203F-\u2040-]*
        )
    # Closing ;
    ;
    """,
    re.VERBOSE,
)

RST_REF_MATCH = re.compile(
    r"(?:(?<=\W)|^)((:[a-z:]+:)(?:`([^< ][^<]*?[^ ])`|`[^< ][^<]*?<([^<]+?)>`))(?!`)(?=\W|$)"
)
RST_FOOTNOTE_MATCH = re.compile(r"(?:(?<=\W)|^)(\[#[^]]+\]_)(?=\W|$)")
RST_INLINE_LINK_MATCH = re.compile(r"(?:(?<=\W)|^)(`[^`<]*[^` <] <[^`> ]*>`_)(?=\W|$)")
RST_LINK_MATCH = re.compile(r"(?:(?<=\W)|^)(`[^`<]*[^` <]`_)(?=\W|$)")


# These should be present in translation if present in source, but might be translated
RST_TRANSLATABLE = {
    ":guilabel:",
    ":file:",
    ":code:",
    ":math:",
    ":eq:",
    ":abbr:",
    ":dfn:",
    ":menuselection:",
    ":sub:",
    ":sup:",
    ":kbd:",
    ":index:",
    ":samp:",
}

RST_ROLE_RE = [
    re.compile(r"""Unknown interpreted text role "([^"]*)"\."""),
    re.compile(r"""Interpreted text role "([^"]*)" not implemented\."""),
]


def strip_entities(text):
    """Strip all HTML entities (we don't care about them)."""
    return XML_ENTITY_MATCH.sub(" ", text)


class BBCodeCheck(TargetCheck):
    """Check for matching bbcode tags."""

    check_id = "bbcode"
    name = gettext_lazy("BBCode markup")
    description = gettext_lazy("BBCode in translation does not match source.")
    default_disabled = True

    def __init__(self) -> None:
        super().__init__()
        self.enable_string = "bbcode-text"

    def check_single(self, source: str, target: str, unit: Unit):
        # Parse source
        src_match = BBCODE_MATCH.findall(source)

        # Parse target
        tgt_match = BBCODE_MATCH.findall(target)
        if len(src_match) != len(tgt_match):
            return True

        src_tags = {x[1] for x in src_match}
        tgt_tags = {x[1] for x in tgt_match}

        return src_tags != tgt_tags

    def check_highlight(self, source: str, unit: Unit):
        if self.should_skip(unit):
            return
        for match in BBCODE_MATCH.finditer(source):
            for tag in ("start", "end"):
                yield match.start(tag), match.end(tag), match.group(tag)


class BaseXMLCheck(TargetCheck):
    def detect_xml_wrapping(self, text: str) -> tuple[_Element, bool]:
        """Detect whether wrapping is desired."""
        try:
            return self.parse_xml(text, True), True
        except SyntaxError:
            return self.parse_xml(text, False), False

    def can_parse_xml(self, text: str) -> bool:
        try:
            self.detect_xml_wrapping(text)
        except SyntaxError:
            return False
        return True

    def parse_xml(self, text: str, wrap: bool) -> _Element:
        """Parse XML."""
        text = strip_entities(text)
        if wrap:
            text = f"<weblate>{text}</weblate>"
        return parse_xml(text.encode() if "encoding" in text else text)

    def should_skip(self, unit: Unit) -> bool:
        if super().should_skip(unit):
            return True

        flags = unit.all_flags

        if "safe-html" in flags:
            return True

        if "xml-text" in flags:
            return False

        sources = unit.get_source_plurals()

        # Quick check if source looks like XML.
        if all(
            "<" not in source or not XML_MATCH.findall(source) for source in sources
        ):
            return True

        # Actually verify XML parsing
        return not all(self.can_parse_xml(source) for source in sources)

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        """Check for single phrase, not dealing with plurals."""
        raise NotImplementedError


class XMLValidityCheck(BaseXMLCheck):
    """Check whether XML in target is valid."""

    check_id = "xml-invalid"
    name = gettext_lazy("XML syntax")
    description = gettext_lazy("The translation is not valid XML.")

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        # Check if source is XML
        try:
            wrap = self.detect_xml_wrapping(source)[1]
        except SyntaxError:
            # Source is not valid XML, we give up
            return False

        # Check target
        try:
            self.parse_xml(target, wrap)
        except SyntaxError:
            # Target is not valid XML
            return True

        return False


class XMLTagsCheck(BaseXMLCheck):
    """Check whether XML in target matches source."""

    check_id = "xml-tags"
    name = gettext_lazy("XML markup")
    description = gettext_lazy("XML tags in translation do not match source.")

    def check_single(self, source: str, target: str, unit: Unit):
        # Check if source is XML
        try:
            source_tree, wrap = self.detect_xml_wrapping(source)
            source_tags = [(x.tag, x.keys()) for x in source_tree.iter()]
        except SyntaxError:
            # Source is not valid XML, we give up
            return False

        # Check target
        try:
            target_tree = self.parse_xml(target, wrap)
            target_tags = [(x.tag, x.keys()) for x in target_tree.iter()]
        except SyntaxError:
            # Target is not valid XML
            return False

        # Compare tags
        return source_tags != target_tags

    def check_highlight(self, source: str, unit: Unit):
        if self.should_skip(unit):
            return []
        if not self.can_parse_xml(source):
            return []
        # Include XML markup
        ret = [
            (match.start(), match.end(), match.group())
            for match in XML_MATCH.finditer(source)
        ]
        # Add XML entities
        skipranges = [x[:2] for x in ret]
        skipranges.append((len(source), len(source)))
        offset = 0
        for match in XML_ENTITY_MATCH.finditer(source):
            start = match.start()
            end = match.end()
            while skipranges[offset][1] < end:
                offset += 1
            # Avoid including entities inside markup
            if start > skipranges[offset][0] and end < skipranges[offset][1]:
                continue
            ret.append((start, end, match.group()))
        return ret


class MarkdownBaseCheck(TargetCheck):
    default_disabled = True

    def __init__(self) -> None:
        super().__init__()
        self.enable_string = "md-text"


class MarkdownRefLinkCheck(MarkdownBaseCheck):
    check_id = "md-reflink"
    name = gettext_lazy("Markdown references")
    description = gettext_lazy("Markdown link references do not match source.")

    def check_single(self, source: str, target: str, unit: Unit):
        src_match = MD_REFLINK.findall(source)
        if not src_match:
            return False
        tgt_match = MD_REFLINK.findall(target)

        src_tags = {x[1] for x in src_match}
        tgt_tags = {x[1] for x in tgt_match}

        return src_tags != tgt_tags


class MarkdownLinkCheck(MarkdownBaseCheck):
    check_id = "md-link"
    name = gettext_lazy("Markdown links")
    description = gettext_lazy("Markdown links do not match source.")

    def check_single(self, source: str, target: str, unit: Unit):
        src_match = MD_LINK.findall(source)
        if not src_match:
            return False
        tgt_match = MD_LINK.findall(target)

        # Check number of links
        if len(src_match) != len(tgt_match):
            return True

        # We don't check actual remote link targets as those might
        # be localized as well (consider links to Wikipedia).
        # Instead we check only relative links and templated ones.
        link_start = (".", "#", "{")
        tgt_anchors = {x[2] for x in tgt_match if x[2] and x[2][0] in link_start}
        src_anchors = {x[2] for x in src_match if x[2] and x[2][0] in link_start}
        return tgt_anchors != src_anchors

    def get_fixup(self, unit: Unit):
        if MD_BROKEN_LINK.findall(unit.target):
            return [(MD_BROKEN_LINK.pattern, "](")]
        return None


class MarkdownSyntaxCheck(MarkdownBaseCheck):
    check_id = "md-syntax"
    name = gettext_lazy("Markdown syntax")
    description = gettext_lazy("Markdown syntax does not match source.")

    @staticmethod
    def extract_match(match):
        for i in range(6):
            if match[i]:
                return match[i]
        return None

    def check_single(self, source: str, target: str, unit: Unit):
        src_tags = {self.extract_match(x) for x in MD_SYNTAX.findall(source)}
        tgt_tags = {self.extract_match(x) for x in MD_SYNTAX.findall(target)}

        return src_tags != tgt_tags

    def check_highlight(self, source: str, unit: Unit):
        if self.should_skip(unit):
            return
        for match in MD_SYNTAX.finditer(source):
            value = ""
            for i in range(MD_SYNTAX_GROUPS):
                value = match.group(i + 1)
                if value:
                    break
            start = match.start()
            end = match.end()
            yield (start, start + len(value), value)
            yield ((end - len(value), end, value if value != "<" else ">"))


class URLCheck(TargetCheck):
    check_id = "url"
    name = gettext_lazy("URL")
    description = gettext_lazy("The translation does not contain an URL.")
    default_disabled = True

    @cached_property
    def validator(self):
        return URLValidator()

    def check_single(self, source: str, target: str, unit: Unit) -> bool:
        if not source:
            return False
        try:
            self.validator(target)  # pylint: disable=too-many-function-args
        except ValidationError:
            return True
        return False


class SafeHTMLCheck(TargetCheck):
    check_id = "safe-html"
    name = gettext_lazy("Unsafe HTML")
    description = gettext_lazy("The translation uses unsafe HTML markup.")
    default_disabled = True

    def check_single(self, source: str, target: str, unit: Unit):
        # Strip MarkDown links
        if "md-text" in unit.all_flags:
            target = MD_LINK.sub("", target)

        sanitizer = HTMLSanitizer()
        cleaned_target = sanitizer.clean(target, source, unit.all_flags)

        return cleaned_target != target


class RSTBaseCheck(TargetCheck):
    default_disabled = True

    def __init__(self) -> None:
        super().__init__()
        self.enable_string = "rst-text"


class RSTReferencesCheck(RSTBaseCheck):
    check_id = "rst-references"
    name = gettext_lazy("Inconsistent reStructuredText references")
    description = gettext_lazy(
        "Inconsistent reStructuredText term references in the translated message."
    )

    def extract_references(self, text: str) -> tuple[dict[str, str], Counter]:
        result: list[tuple[str, str]] = [
            (
                role if role in RST_TRANSLATABLE else f"{role}{target or named_target}",
                text,
            )
            for text, role, target, named_target in RST_REF_MATCH.findall(text)
        ]
        result.extend(
            (footnote, footnote) for footnote in RST_FOOTNOTE_MATCH.findall(text)
        )
        return dict(result), Counter(item[0] for item in result)

    def check_single(
        self, source: str, target: str, unit: Unit
    ) -> bool | MissingExtraDict:
        src_references, src_set = self.extract_references(source)
        tgt_references, tgt_set = self.extract_references(target)

        errors: list[str] = []

        missing = src_set - tgt_set
        extra = tgt_set - src_set

        src_links = len(RST_INLINE_LINK_MATCH.findall(source))
        tgt_links = len(RST_INLINE_LINK_MATCH.findall(target))
        if src_links != tgt_links:
            errors.append(
                gettext("Inconsistent inline links in the translated message.")
            )
        src_links = len(RST_LINK_MATCH.findall(source))
        tgt_links = len(RST_LINK_MATCH.findall(target))
        if src_links != tgt_links:
            errors.append(
                gettext("Inconsistent external links in the translated message.")
            )
        if missing or extra or errors:
            return {
                "missing": list(
                    chain.from_iterable(
                        [src_references[item]] if src_set[item] == 1 else [item] * count
                        for item, count in missing.items()
                    )
                ),
                "extra": list(
                    chain.from_iterable(
                        [tgt_references[item]] if tgt_set[item] == 1 else [item] * count
                        for item, count in extra.items()
                    )
                ),
                "errors": errors,
            }
        return False

    def get_description(self, check_obj: Check) -> StrOrPromise:
        unit = check_obj.unit

        errors: list[StrOrPromise] = []
        results: MissingExtraDict = defaultdict(list)

        # Merge plurals
        for result in self.check_target_generator(
            unit.get_source_plurals(), unit.get_target_plurals(), unit
        ):
            if isinstance(result, dict):
                for key, value in result.items():
                    results[key].extend(value)
        if results:
            errors.extend(self.format_result(results))
        if errors:
            return format_html_join(
                mark_safe("<br />"),
                "{}",
                ((error,) for error in errors),
            )
        return super().get_description(check_obj)

    def check_highlight(self, source: str, unit: Unit):
        if self.should_skip(unit):
            return
        for match in chain(
            RST_REF_MATCH.finditer(source), RST_FOOTNOTE_MATCH.finditer(source)
        ):
            yield match.start(0), match.end(0), match.group(0)


@cache
def get_rst_publisher() -> Publisher:
    publisher = Publisher(settings=None)
    publisher.set_components("standalone", "restructuredtext", "null")
    publisher.get_settings(
        # Never halt parsing with an exception
        halt_level=5,
        # Do not allow file insertion
        file_insertion_enabled=False,
        # Following are needed in case django.contrib.admindocs is imported
        # and registers own rst tags
        default_reference_context="",
        link_base="",
    )
    return publisher


@lru_cache(maxsize=512)
def validate_rst_snippet(
    snippet: str, source_tags: tuple[str] | None = None
) -> tuple[list[str], list[str]]:
    publisher = get_rst_publisher()
    document = utils.new_document(None, publisher.settings)
    document.reporter.stream = None

    errors: list[str] = []
    roles: list[str] = []

    def error_collector(data: system_message) -> None:
        """Save the error."""
        message = Element.astext(data)
        if message.startswith("Unknown target name:") and "`" not in message:
            # Translating targets is okay, just catch obvious errors
            return
        if message.startswith(
            (
                # Duplicates Unknown interpreted in our case
                "No role entry",
                # Can not work on snippets
                "Too many autonumbered footnote",
                # Can not work on snippets
                "Enumerated list start value not ordinal",
            )
        ):
            return
        for rst_role_re in RST_ROLE_RE:
            if match := rst_role_re.match(message):
                role = match.group(1)
                roles.append(role)
                if source_tags is not None and role in source_tags:
                    # Skip if the role was found in the source
                    return
        errors.append(message)

    document.reporter.attach_observer(error_collector)
    publisher.reader.parser.parse(snippet, document)
    transformer = document.transformer
    transformer.populate_from_components(
        (
            publisher.source,
            publisher.reader,
            publisher.reader.parser,
            publisher.writer,
            publisher.destination,
        )
    )
    while transformer.transforms:
        if not transformer.sorted:
            # Unsorted initially, and whenever a transform is added.
            transformer.transforms.sort()
            transformer.transforms.reverse()
            transformer.sorted = 1
        priority, transform_class, pending, kwargs = transformer.transforms.pop()
        transform = transform_class(transformer.document, startnode=pending)
        transform.apply(**kwargs)
        transformer.applied.append((priority, transform_class, pending, kwargs))
    return errors, roles


class RSTSyntaxCheck(RSTBaseCheck):
    check_id = "rst-syntax"
    name = gettext_lazy("reStructuredText syntax error")
    description = gettext_lazy("reStructuredText syntax error in the translation.")

    def check_single(
        self, source: str, target: str, unit: Unit
    ) -> bool | MissingExtraDict:
        _errors, source_roles = validate_rst_snippet(source)
        errors, _target_roles = validate_rst_snippet(target, tuple(source_roles))

        if errors:
            return {"errors": errors}
        return False

    def get_description(self, check_obj: Check) -> StrOrPromise:
        unit = check_obj.unit

        errors: list[StrOrPromise] = []
        results: MissingExtraDict = defaultdict(list)

        # Merge plurals
        for result in self.check_target_generator(
            unit.get_source_plurals(), unit.get_target_plurals(), unit
        ):
            if isinstance(result, dict):
                for key, value in result.items():
                    results[key].extend(value)
        if results:
            errors.extend(self.format_result(results))
        if errors:
            return format_html_join(
                mark_safe("<br />"),
                "{}",
                ((error,) for error in errors),
            )
        return super().get_description(check_obj)
