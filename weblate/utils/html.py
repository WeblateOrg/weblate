# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
import threading
from collections import defaultdict
from html.parser import HTMLParser as StdHTMLParser
from typing import TYPE_CHECKING, Any

import nh3
from django.utils.html import format_html, format_html_join
from django.utils.translation import pgettext
from html2text import HTML2Text as _HTML2Text
from lxml.etree import HTMLParser
from lxml.html.defs import tags as lxml_html_tags

if TYPE_CHECKING:
    from collections.abc import Iterable

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
    (`+)\s*(?:[\s\S]*?[^`])\s*\5(?!`)   # `code`
    |
    (~~)(?=\S)(?:[\s\S]*?\S)~~          # ~~word~~
    |
    (<)(?:https?://[^>]+)>              # URL
    |
    (<)(?:[^>]+@[^>]+\.[^>]+)>          # E-mail
    """,
    re.VERBOSE,
)
MD_SYNTAX_GROUPS = 8

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
