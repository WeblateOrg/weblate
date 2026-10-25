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
from lxml.etree import HTMLParser
from lxml.html.defs import tags as lxml_html_tags
from turbohtml import Element, PlainText, Text, parse

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

    from django.utils.safestring import SafeString
    from lxml.etree import ParserTarget

    from weblate.checks.flags import Flags
else:
    ParserTarget = object

MD_BROKEN_LINK = re.compile(r"\] +\(")
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


class MarkdownLinkMatch:
    """The match operations needed by checks and HTML sanitization."""

    def __init__(self, text: str, spans: tuple[tuple[int, int], ...]) -> None:
        self.text = text
        self.spans = spans

    def start(self, group: int = 0) -> int:
        return self.spans[group][0]

    def end(self, group: int = 0) -> int:
        return self.spans[group][1]

    def group(self, group: int = 0) -> str:
        start, end = self.spans[group]
        return self.text[start:end] if start >= 0 else ""

    def __getitem__(self, group: int) -> str:
        return self.group(group)

    def groups(self) -> tuple[str, ...]:
        return tuple(self.group(index) for index in range(1, len(self.spans)))


def _next_markdown_quotes(text: str) -> dict[str, list[int]]:
    """Cache unescaped closing delimiters for title candidates."""
    quotes = "\"'\u201c)"
    result = {quote: [-1] * (len(text) + 1) for quote in quotes}
    escaped = bytearray(len(text))
    backslashes = 0
    for position, char in enumerate(text):
        if char == "\\":
            backslashes += 1
        else:
            escaped[position] = backslashes % 2
            backslashes = 0
    next_positions = dict.fromkeys(quotes, -1)
    for position in range(len(text) - 1, -1, -1):
        char = text[position]
        if char in next_positions and not escaped[position]:
            next_positions[char] = position
        for quote in quotes:
            result[quote][position] = next_positions[quote]
    return result


def _consume_markdown_quote(
    start: int, quote: str, next_quotes: dict[str, list[int]]
) -> tuple[int, int]:
    """Return the end of a title candidate and its first unescaped parenthesis."""
    closing = next_quotes[quote][start + 1]
    first_closing = next_quotes[")"][start + 1]
    if closing == -1:
        return -1, first_closing
    return closing + 1, first_closing if first_closing <= closing else -1


def _after_markdown_angle_destination(
    text: str, opening: int, next_angle_closing: list[int]
) -> int:
    position = opening + 1
    while position < len(text) and text[position].isspace():
        position += 1
    if position < len(text) and text[position] == "<":
        closing = next_angle_closing[position + 1]
        if closing != -1:
            return closing + 1
    return opening + 1


def _markdown_destination_ends(
    text: str, next_quotes: dict[str, list[int]], next_nonspace: list[int]
) -> list[tuple[int, int, int] | None]:
    """Cache the closing parenthesis and optional title for every suffix."""
    results: list[tuple[int, int, int] | None] = [None] * (len(text) + 1)
    for position in range(len(text) - 1, -1, -1):
        char = text[position]
        if char == ")":
            results[position] = (position, -1, -1)
        elif char in "\"'(\u201c" and position > 0 and text[position - 1].isspace():
            quote = ")" if char == "(" else char
            after, first_closing = _consume_markdown_quote(position, quote, next_quotes)
            suffix = next_nonspace[after] if after != -1 else -1
            if suffix < len(text) and suffix != -1 and text[suffix] == ")":
                results[position] = (suffix, position, after)
            elif first_closing != -1:
                results[position] = (first_closing, -1, -1)
            elif after != -1:
                results[position] = results[suffix]
        else:
            results[position] = results[position + 1]
    return results


def _parse_markdown_destination(
    text: str,
    opening: int,
    last_closing: int,
    next_angle_closing: list[int],
    destination_ends: list[tuple[int, int, int] | None],
) -> tuple[int, tuple[int, int], tuple[int, int], tuple[int, int]] | None:
    """Return the closing position and spans for angle, URL, and title."""
    if opening >= last_closing:
        return None
    position = _after_markdown_angle_destination(text, opening, next_angle_closing)
    if position > last_closing:
        return None
    # The first URL character cannot be a title opener.
    if position == opening + 1 and text[position] != ")":
        position += 1
    result = destination_ends[position]
    if result is None:
        return None
    position, title_start, title_end = result

    url_start = opening + 1
    while url_start < position and text[url_start].isspace():
        url_start += 1
    url_end = title_start if title_start != -1 else position
    while url_end > url_start and text[url_end - 1].isspace():
        url_end -= 1
    angle = (-1, -1)
    if url_end - url_start >= 2 and text[url_start] == "<" and text[url_end - 1] == ">":
        angle = (url_start, url_start + 1)
        url_start += 1
        url_end -= 1
    return position + 1, angle, (url_start, url_end), (title_start, title_end)


def _markdown_destination_boundaries(text: str) -> tuple[list[int], list[int]]:
    next_angle_closing = [-1] * (len(text) + 1)
    next_nonspace = [len(text)] * (len(text) + 1)
    closing = -1
    nonspace = len(text)
    for index in range(len(text) - 1, -1, -1):
        if text[index] == ">":
            closing = index
        next_angle_closing[index] = closing
        if not text[index].isspace():
            nonspace = index
        next_nonspace[index] = nonspace
    return next_angle_closing, next_nonspace


def _iter_markdown_bracket_links(
    text: str, *, reference: bool
) -> Iterator[MarkdownLinkMatch]:
    """Scan bracket pairs once, including malformed prefixes."""
    openings: list[int] = []
    candidates: list[MarkdownLinkMatch | None] = [None] * len(text)
    # An unterminated destination can be rejected without scanning its tail.
    last_closing = text.rfind(")") if not reference else -1
    next_angle_closing: list[int] = []
    next_nonspace: list[int] = []
    next_quotes: dict[str, list[int]] = {}
    destination_ends: list[tuple[int, int, int] | None] = []
    if not reference:
        next_quotes = _next_markdown_quotes(text)
        next_angle_closing, next_nonspace = _markdown_destination_boundaries(text)
        destination_ends = _markdown_destination_ends(text, next_quotes, next_nonspace)
    position = 0
    while position < len(text):
        if text[position] == "[":
            openings.append(position)
        elif text[position] == "]" and openings:
            after = position + 1
            spans: tuple[tuple[int, int], ...]
            if reference:
                while after < len(text) and text[after].isspace():
                    after += 1
                marker = after < len(text) and text[after] == "["
            else:
                marker = after < len(text) and text[after] == "("
            if not marker:
                if len(openings) > 1:
                    openings.pop()
                position += 1
                continue
            opening = openings.pop()
            if reference:
                closing = text.find("]", after + 1)
                if closing == -1:
                    position += 1
                    continue
                end = closing + 1
                spans = (
                    (opening - (opening > 0 and text[opening - 1] == "!"), end),
                    (opening + 1, position),
                    (after + 1, closing),
                )
            else:
                parsed = _parse_markdown_destination(
                    text,
                    after,
                    last_closing,
                    next_angle_closing,
                    destination_ends,
                )
                if parsed is None:
                    position += 1
                    continue
                end, angle, url, title = parsed
                spans = (
                    (opening - (opening > 0 and text[opening - 1] == "!"), end),
                    (opening + 1, position),
                    angle,
                    url,
                    title,
                    (-1, -1),
                    (-1, -1),
                )
            candidates[spans[0][0]] = MarkdownLinkMatch(text, spans)
            position = end
            continue
        position += 1
    end = 0
    for match in candidates:
        if match is not None and match.start() >= end:
            yield match
            end = match.end()


class MarkdownLinkPattern:
    """Expose the match operations used by existing Markdown callers."""

    def __init__(self, *, reference: bool = False) -> None:
        self.reference = reference

    def finditer(self, text: str) -> Iterator[MarkdownLinkMatch]:
        brackets = _iter_markdown_bracket_links(text, reference=self.reference)
        if self.reference:
            yield from brackets
            return
        autolinks = (
            MarkdownLinkMatch(
                text,
                (
                    (match.start, match.end),
                    *((-1, -1),) * 4,
                    (match.start + 1, match.end - 1)
                    if text.startswith(("<http://", "<https://"), match.start)
                    else (-1, -1),
                    (match.start + 1, match.end - 1)
                    if not text.startswith(("<http://", "<https://"), match.start)
                    else (-1, -1),
                ),
            )
            for match in iter_markdown_autolinks(text)
        )
        end = 0
        for match in merge(brackets, autolinks, key=lambda item: item.start()):
            if match.start() >= end:
                yield match
                end = match.end()

    def findall(self, text: str) -> list[tuple[str, ...]]:
        return [
            tuple(group or "" for group in match.groups())
            for match in self.finditer(text)
        ]

    def fullmatch(self, text: str) -> MarkdownLinkMatch | None:
        match = next(self.finditer(text), None)
        return (
            match
            if match is not None and match.start() == 0 and match.end() == len(text)
            else None
        )

    def sub(
        self, replacement: str | Callable[[MarkdownLinkMatch], str], text: str
    ) -> str:
        parts: list[str] = []
        position = 0
        for match in self.finditer(text):
            parts.extend(
                (
                    text[position : match.start()],
                    replacement(match) if callable(replacement) else replacement,
                )
            )
            position = match.end()
        parts.append(text[position:])
        return "".join(parts)


MD_LINK = MarkdownLinkPattern()
MD_REFLINK = MarkdownLinkPattern(reference=True)


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
    <!--(?:(?!<!--)[\s\S])*?-->
    |
    <!DOCTYPE(?:\s++|"[^"]*"|'[^']*'|[^<\s'">]++)*+\??>
    |
    </?[A-Za-z](?:[^<>"']++|"[^"]*"|'[^']*')*+>
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
SPECIAL_TOKEN = re.compile(r"@@@@@weblate:[0-9]+@@@@@")
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

    def handle_replace(self, match: re.Match[str] | MarkdownLinkMatch) -> str:
        self.current += 1
        replacement = f"@@@@@weblate:{self.current}@@@@@"
        self.replacements[replacement] = match.group(0)
        return replacement

    def remove_special(self, text: str, flags: Flags) -> str:
        if "md-text" in flags:
            text = MD_LINK.sub(self.handle_replace, text)

        return SANE_CHARS.sub(self.handle_replace, text)

    def add_back_special(self, text: str) -> str:
        if not self.replacements:
            return text
        return SPECIAL_TOKEN.sub(
            lambda match: self.replacements.get(match.group(0), match.group(0)), text
        )


MAIL_TEXT_OPTIONS = PlainText(width=78, links="inline", images=False, layout="strict")


def _table_colspan(cell: Element) -> int:
    colspan = cell.attrs.get("colspan")
    return max(1, int(colspan)) if isinstance(colspan, str) and colspan.isdigit() else 1


def html_to_mail_text(html: str) -> str:
    """Render notification HTML as plain text, retaining Weblate diff notation."""
    document = parse(html)

    for element in document.select("ins, del"):
        opening, closing = ("{+", "+}") if element.tag == "ins" else ("[-", "-]")
        element.insert_before(Text(opening))
        element.insert_after(Text(closing))
        element.unwrap()

    for table in document.select("table"):
        if all(
            len(line) <= 78 for line in table.to_text(MAIL_TEXT_OPTIONS).splitlines()
        ):
            continue
        header_row = table.select_one("thead tr")
        headers = []
        if header_row is not None:
            for cell in header_row.select("th"):
                headers.extend(
                    [cell.to_text(MAIL_TEXT_OPTIONS).strip()] * _table_colspan(cell)
                )
        rows = []
        for row in table.select("tr"):
            if row == header_row:
                continue
            cells = row.select("th, td")
            if cells:
                content: list[Element | Text]
                if headers:
                    content = []
                    column = 0
                    for cell in cells:
                        if content:
                            content.append(Element("br"))
                        span = _table_colspan(cell)
                        label = (
                            headers[column]
                            if span == 1 and column < len(headers)
                            else ""
                        )
                        value = cell.to_text(MAIL_TEXT_OPTIONS).strip()
                        content.append(Text(f"{label}: {value}" if label else value))
                        column += span
                else:
                    values = [cell.to_text(MAIL_TEXT_OPTIONS).strip() for cell in cells]
                    content = [
                        Text(
                            f"{values[0]}: {'; '.join(values[1:])}"
                            if len(values) > 1
                            else values[0]
                        )
                    ]
                rows.append(
                    Element(
                        "p",
                        children=content,
                    )
                )
        table.replace_with(Element("div", children=rows))

    return document.to_text(MAIL_TEXT_OPTIONS)


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
