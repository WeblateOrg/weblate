# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
import threading
from collections import defaultdict
from heapq import merge
from html.parser import HTMLParser as StdHTMLParser
from typing import TYPE_CHECKING, Any, NamedTuple

import nh3
from django.utils.html import format_html, format_html_join
from django.utils.translation import pgettext
from html2text import HTML2Text as _HTML2Text
from lxml.etree import HTMLParser
from lxml.html.defs import tags as lxml_html_tags

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from django.utils.safestring import SafeString
    from lxml.etree import ParserTarget

    from weblate.checks.flags import Flags
else:
    ParserTarget = object

MD_LINK = re.compile(
    r"""
    (?:
    !?                                                          # Exclamation for images
    \[((?:\[[^^\]]*\]|[^\[\]]|\](?=[^\[]*\]))*)\]               # Link text
    \(
        \s*(<)?([\s\S]*?)(?(2)>)                                # URL
        (?:\s+['"]([\s\S]*?)['"])?\s*                           # Title
    \)
    |
    <(https?://[^>]+)>                                          # URL
    |
    <([^>]+@[^>]+\.[^>]+)>                                      # E-mail
    )
    """,
    re.VERBOSE,
)
MD_BROKEN_LINK = re.compile(r"\] +\(")
MD_REFLINK = re.compile(
    r"!?\[("  # leading [
    r"(?:\[[^^\]]*\]|[^\[\]]|\](?=[^\[]*\]))*"  # link text
    r")\]\s*\[([^^\]]*)\]"  # trailing ] with optional target
)
MD_SYNTAX = re.compile(
    r"""
    (_{2})(?:[\s\S]+?)_{2}(?!_)         # __word__
    |
    (\*{2})(?:[\s\S]+?)\*{2}(?!\*)      # **word**
    |
    \b(_)(?:(?:__|[^_])+?)_\b           # _word_
    |
    (\*)(?:(?:\*\*|[^\*])+?)\*(?!\*)    # *word*
    |
    (~~)(?=\S)(?:[\s\S]*?\S)~~          # ~~word~~
    """,
    re.VERBOSE,
)


class MarkdownSyntax(NamedTuple):
    start: int
    end: int
    value: str


def _is_markdown_autolink(value: str) -> bool:
    """Return whether an angle-delimited value is a supported autolink."""
    if value.startswith("http://"):
        return len(value) > 7
    if value.startswith("https://"):
        return len(value) > 8

    has_at = False
    characters_after_at = 0
    for position, character in enumerate(value):
        if not has_at:
            if character == "@" and position > 0:
                has_at = True
        else:
            if character == "." and characters_after_at and position + 1 < len(value):
                return True
            characters_after_at += 1
    return False


def iter_markdown_autolinks(text: str) -> Iterator[MarkdownSyntax]:
    """Yield supported Markdown autolinks in one pass."""
    opening: int | None = None
    backslashes = 0
    for position, character in enumerate(text):
        if character == "\\":
            backslashes += 1
            continue
        escaped = backslashes % 2 == 1
        backslashes = 0
        if character == "<" and not escaped:
            opening = position
        elif character == ">" and opening is not None:
            if _is_markdown_autolink(text[opening + 1 : position]):
                yield MarkdownSyntax(opening, position + 1, "<")
            opening = None


def _iter_markdown_code_spans(
    text: str, excluded_opening_ranges: Iterable[tuple[int, int]]
) -> Iterator[MarkdownSyntax]:
    """Yield Markdown code spans without reconsidering backtick runs."""
    runs: list[tuple[int, int, bool, bool]] = []
    position = 0
    length = len(text)
    backslashes = 0
    while position < length:
        if text[position] != "`":
            if text[position] == "\\":
                backslashes += 1
            else:
                backslashes = 0
            position += 1
            continue
        end = position + 1
        while end < length and text[end] == "`":
            end += 1
        if backslashes % 2:
            # A backslash escapes the first tick outside a code span. Preserve
            # the maximal run as a possible closer, where escapes are literal,
            # and expose the remaining suffix as a possible opener.
            runs.append((position, end, False, True))
            if position + 1 < end:
                runs.append((position + 1, end, True, False))
        else:
            runs.append((position, end, True, True))
        position = end
        backslashes = 0

    next_run: list[int | None] = [None] * len(runs)
    last_by_length: dict[int, int] = {}
    for index in range(len(runs) - 1, -1, -1):
        start, end, _can_open, can_close = runs[index]
        run_length = end - start
        next_run[index] = last_by_length.get(run_length)
        if can_close:
            last_by_length[run_length] = index

    excluded_ranges = iter(excluded_opening_ranges)
    excluded_start, excluded_end = next(excluded_ranges, (length, length))
    index = 0
    while index < len(runs):
        start, opening_end, can_open, _can_close = runs[index]
        while excluded_end <= start:
            excluded_start, excluded_end = next(excluded_ranges, (length, length))
        if not can_open or excluded_start <= start < excluded_end:
            index += 1
            continue
        closing_index = next_run[index]
        if closing_index is None:
            index += 1
            continue
        _closing_start, end, _can_open, _can_close = runs[closing_index]
        yield MarkdownSyntax(start, end, text[start:opening_end])
        index = closing_index + 1
        while index < len(runs) and runs[index][0] < end:
            index += 1


def iter_markdown_code_spans(text: str) -> Iterator[MarkdownSyntax]:
    """Yield Markdown code spans without reconsidering backtick runs."""
    autolinks = list(iter_markdown_autolinks(text))
    yield from _iter_markdown_code_spans(
        text, ((match.start, match.end) for match in autolinks)
    )


def iter_markdown_syntax(text: str) -> Iterator[MarkdownSyntax]:
    """Yield Markdown syntax while treating code spans as opaque text."""
    autolinks = list(iter_markdown_autolinks(text))
    code_spans = list(
        _iter_markdown_code_spans(
            text, ((match.start, match.end) for match in autolinks)
        )
    )
    code_span_index = 0
    visible_autolinks: list[MarkdownSyntax] = []
    for autolink in autolinks:
        while (
            code_span_index < len(code_spans)
            and code_spans[code_span_index].end <= autolink.start
        ):
            code_span_index += 1
        if (
            code_span_index < len(code_spans)
            and code_spans[code_span_index].start
            < autolink.start
            < code_spans[code_span_index].end
        ):
            # A code span starting before an apparent autolink takes precedence.
            continue
        visible_autolinks.append(autolink)

    opaque_syntax = list(
        merge(code_spans, visible_autolinks, key=lambda match: match.start)
    )
    if opaque_syntax:
        masked_parts: list[str] = []
        position = 0
        for span in opaque_syntax:
            masked_parts.extend(
                (text[position : span.start], "x" * (span.end - span.start))
            )
            position = span.end
        masked_parts.append(text[position:])
        masked = "".join(masked_parts)
    else:
        masked = text

    regex_syntax = (
        MarkdownSyntax(
            match.start(),
            match.end(),
            next((group for group in match.groups() if group), ""),
        )
        for match in MD_SYNTAX.finditer(masked)
    )
    yield from merge(regex_syntax, opaque_syntax, key=lambda match: match.start)


AUTO_SAFE_HTML_START = re.compile(r"<(?=[!/?A-Za-z])")
AUTO_SAFE_HTML_SEGMENT = re.compile(
    r"""
    <!--[\s\S]*?-->
    |
    <!DOCTYPE(?:\s+(?:"[^"]*"|'[^']*'|[^'">])*)?>
    |
    </?[A-Za-z](?:[^<>"']|"[^"]*"|'[^']*')*?>
    """,
    re.IGNORECASE | re.VERBOSE,
)
AUTO_SAFE_HTML_TAG_NAME = re.compile(
    r"</?\s*(?P<name>[A-Za-z][A-Za-z0-9:-]*)",
    re.IGNORECASE,
)
AUTO_SAFE_HTML_CUSTOM_ELEMENT = re.compile(
    r"[a-z][a-z0-9._-]*-[a-z0-9._-]*\Z",
)
AUTO_SAFE_HTML_STANDARD_TAG_NAMES = {
    "dialog",
    "main",
    "picture",
    "search",
    "slot",
    "template",
}
AUTO_SAFE_HTML_TAG_NAMES = frozenset(
    {tag.lower() for tag in lxml_html_tags}
    | set(nh3.ALLOWED_TAGS)
    | AUTO_SAFE_HTML_STANDARD_TAG_NAMES
)
AUTO_SAFE_HTML_VOID_TAGS = frozenset(
    {
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
        "param",
        "source",
        "track",
        "wbr",
    }
)

IGNORE = {"body", "html"}
CLEAN_CONTENT_TAGS = {"script", "style"}

# Allow some chars:
# - non breakable space
SANE_CHARS = re.compile(r"[\xa0]")
NH3_LOCK = threading.Lock()


class MarkupExtractor(ParserTarget):
    def __init__(self) -> None:
        self.found_tags: set[str] = set()
        self.found_attributes: dict[str, set[str]] = defaultdict(set)

    def start(self, tag: str, attrs: dict[str, str]) -> None:  # type: ignore[override]
        if tag in IGNORE:
            return
        self.found_tags.add(tag)
        self.found_attributes[tag].update(attrs.keys())

    def close(self) -> None:
        pass


class HTMLAttribute(NamedTuple):
    tag: str
    name: str
    value: str | None


class HTMLAttributeExtractor(StdHTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.attributes: list[HTMLAttribute] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_attributes(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_attributes(tag, attrs)

    def handle_attributes(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in IGNORE:
            return
        self.attributes.extend(HTMLAttribute(tag, name, value) for name, value in attrs)


def extract_html_tags(text: str) -> tuple[set[str], dict[str, set[str]]]:
    """Extract tags from text in a form suitable for HTML sanitization."""
    extractor = MarkupExtractor()
    if "<body" not in text.lower():
        # Make sure we are in body, otherwise HTML parser migght halluciate we
        # are in <head>
        text = f"<body>{text}</body>"
    parser = HTMLParser(collect_ids=False, target=extractor)
    parser.feed(text)
    return (extractor.found_tags, extractor.found_attributes)


def extract_html_attributes(text: str) -> list[HTMLAttribute]:
    """Extract ordered HTML attributes from a text fragment."""
    extractor = HTMLAttributeExtractor()
    extractor.feed(text)
    extractor.close()
    return extractor.attributes


def is_auto_safe_html_source(source: str, flags: Flags) -> bool:
    """
    Return whether auto-safe-html should treat the source as HTML-aware.

    This enables sanitization for plain text, standard HTML, and custom elements.

    It disables sanitization for invalid tag-like markup and for other markup
    syntaxes such as JSX or MDX components. Exotic markup such as SVG or MathML
    needs an explicit safe-html flag.
    """
    if "md-text" in flags:
        source = MD_LINK.sub("", source)

    if AUTO_SAFE_HTML_START.search(source) is None:
        return True

    segments = list(AUTO_SAFE_HTML_SEGMENT.finditer(source))
    if not segments:
        return False

    segment_spans = [(segment.start(), segment.end()) for segment in segments]
    if any(
        not any(start <= start_match.start() < end for start, end in segment_spans)
        for start_match in AUTO_SAFE_HTML_START.finditer(source)
    ):
        return False

    if not all(is_auto_safe_html_segment(segment.group(0)) for segment in segments):
        return False

    sanitizer = HTMLSanitizer()
    return is_auto_safe_html_roundtrip_stable(
        source, sanitizer.clean(source, source, flags)
    )


def is_auto_safe_html_segment(segment: str) -> bool:
    """Validate a single tag-like segment for auto-safe-html."""
    if "{" in segment or "}" in segment:
        return False

    lower_segment = segment.lower()
    if lower_segment.startswith(("<!--", "<!doctype")):
        return True

    match = AUTO_SAFE_HTML_TAG_NAME.match(segment)
    if match is None:
        return False

    return is_auto_safe_html_tag_name(match.group("name"))


def is_auto_safe_html_tag_name(tag_name: str) -> bool:
    """Check whether a tag name is HTML-like enough for auto-safe-html."""
    lower_name = tag_name.lower()
    return (
        lower_name in AUTO_SAFE_HTML_TAG_NAMES
        or AUTO_SAFE_HTML_CUSTOM_ELEMENT.fullmatch(lower_name) is not None
    )


class AutoSafeHTMLRoundtripParser(StdHTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.events.append(("start", tag, normalize_auto_safe_html_attrs(attrs)))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.events.append(("startend", tag, normalize_auto_safe_html_attrs(attrs)))

    def handle_endtag(self, tag: str) -> None:
        self.events.append(("end", tag))

    def handle_data(self, data: str) -> None:
        if data:
            self.events.append(("data", data))

    def handle_comment(self, data: str) -> None:
        self.events.append(("comment", data))

    def handle_decl(self, decl: str) -> None:
        self.events.append(("decl", decl))


def normalize_auto_safe_html_attrs(
    attrs: list[tuple[str, str | None]],
) -> tuple[tuple[str, str | None], ...]:
    return tuple(
        sorted(attrs, key=lambda item: (item[0], "" if item[1] is None else item[1]))
    )


def extract_auto_safe_html_events(source: str) -> list[tuple]:
    parser = AutoSafeHTMLRoundtripParser()
    parser.feed(source)
    parser.close()
    return parser.events


def is_auto_safe_html_roundtrip_stable(source: str, cleaned: str) -> bool:
    source_events = [
        event
        for event in extract_auto_safe_html_events(source)
        if event[0] not in {"comment", "decl"}
    ]
    cleaned_events = [
        event
        for event in extract_auto_safe_html_events(cleaned)
        if event[0] not in {"comment", "decl"}
    ]

    source_pos = 0
    cleaned_pos = 0

    while source_pos < len(source_events) and cleaned_pos < len(cleaned_events):
        source_event = source_events[source_pos]
        cleaned_event = cleaned_events[cleaned_pos]

        if source_event == cleaned_event:
            source_pos += 1
            cleaned_pos += 1
            continue

        if (
            source_event[0] == "startend"
            and cleaned_event[0] == "start"
            and source_event[1:] == cleaned_event[1:]
        ):
            tag_name = source_event[1]
            if tag_name in AUTO_SAFE_HTML_VOID_TAGS or (
                cleaned_pos + 1 < len(cleaned_events)
                and cleaned_events[cleaned_pos + 1] == ("end", tag_name)
            ):
                source_pos += 1
                cleaned_pos += 1
                if cleaned_pos < len(cleaned_events) and cleaned_events[
                    cleaned_pos
                ] == ("end", tag_name):
                    cleaned_pos += 1
                continue

        return False

    return source_pos == len(source_events) and cleaned_pos == len(cleaned_events)


def serialize_mdx_void_elements(text: str) -> str:
    """Serialize HTML void elements as self-closing JSX elements."""

    def replace(match: re.Match) -> str:
        segment = match.group(0)
        if segment.startswith("</"):
            return segment

        tag_match = AUTO_SAFE_HTML_TAG_NAME.match(segment)
        if (
            tag_match is None
            or tag_match.group("name").lower() not in AUTO_SAFE_HTML_VOID_TAGS
        ):
            return segment

        opening = segment[:-1].rstrip().removesuffix("/").rstrip()
        return f"{opening} />"

    return AUTO_SAFE_HTML_SEGMENT.sub(replace, text)


class HTMLSanitizer:
    def __init__(self) -> None:
        self.current = 0
        self.replacements: dict[str, str] = {}

    def clean(self, text: str, source: str, flags: Flags) -> str:
        self.current = 0
        self.replacements = {}

        text = self.remove_special(text, flags)

        tags, attributes = extract_html_tags(source)

        with NH3_LOCK:
            text = nh3.clean(
                text,
                link_rel=None,
                tags=tags,
                attributes=attributes,
                clean_content_tags=CLEAN_CONTENT_TAGS - tags,
            )

        if "safe-mdx" in flags and "ignore-safe-mdx" not in flags:
            text = serialize_mdx_void_elements(text)

        return self.add_back_special(text)

    def handle_replace(self, match: re.Match) -> str:
        self.current += 1
        replacement = f"@@@@@weblate:{self.current}@@@@@"
        self.replacements[replacement] = match.group(0)
        return replacement

    def remove_special(self, text: str, flags: Flags) -> str:
        if "md-text" in flags:
            text = MD_LINK.sub(self.handle_replace, text)

        return SANE_CHARS.sub(self.handle_replace, text)

    def add_back_special(self, text: str) -> str:
        for replacement, original in self.replacements.items():
            text = text.replace(replacement, original)
        return text


# Map tags to open and closing text
WEBLATE_TAGS = {
    # Word diff syntax for text changes
    "ins": ("{+", "+}"),
    "del": ("[-", "-]"),
}


class HTML2Text(_HTML2Text):
    def __init__(self, bodywidth: int = 78) -> None:
        super().__init__(bodywidth=bodywidth)
        # Use Unicode characters instead of their ascii pseudo-replacements
        self.unicode_snob = True
        #  Do not include any formatting for images
        self.ignore_images = True
        # Pad the cells to equal column width in tables
        self.pad_tables = True

    def handle_tag(self, tag: str, attrs: dict[str, str | None], start: bool) -> None:
        # Special handling for certain tags
        if tag in WEBLATE_TAGS:
            self.o(WEBLATE_TAGS[tag][not start])
            return
        super().handle_tag(tag, attrs, start)


def mail_quote_char(text: str) -> str | SafeString:
    if text in {":", "."}:
        return format_html("<span>{}</span>", text)
    return text


def mail_quote_value(text: str) -> str | SafeString:
    """
    Quote value to be used in e-mail notifications.

    This tries to avoid automatic conversion to links by Gmail
    and similar services.

    Solution based on https://stackoverflow.com/a/23404042/225718
    """
    return format_html_join(
        "",
        "{}",
        ((mail_quote_char(part),) for part in re.split(r"([.:])", text)),
    )


def format_html_join_comma(
    format_string: str, args_generator: Iterable[Iterable[Any]]
) -> SafeString:
    return format_html_join(
        pgettext("Joins a list of values", ", "), format_string, args_generator
    )


def list_to_tuples(strings: Iterable[Any]) -> Iterable[tuple[Any]]:
    """Convert a list of strings into a list of single-element tuples."""
    return ((s,) for s in strings)
