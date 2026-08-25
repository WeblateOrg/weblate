# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from collections import defaultdict
from html import escape as html_escape
from typing import TYPE_CHECKING

from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, ngettext, pgettext

from weblate.lang.models import Language
from weblate.trans.models import Category, Component, Project, Translation, Unit
from weblate.trans.specialchars import get_display_char
from weblate.trans.util import split_plural
from weblate.utils.diff import Differ
from weblate.utils.html import format_html_join_comma, list_to_tuples
from weblate.utils.stats import CategoryLanguage, ProjectLanguage
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from collections.abc import Generator

    from django.db.models import Model
    from django_stubs_ext import StrOrPromise

    from weblate.auth.models import User
    from weblate.utils.stats import GhostStats

SPACE_START = '<span class="hlspace"><span class="space-space">'
SPACE_NL_START = '<span class="hlspace"><span class="space-nl">'
SPACE_MIDDLE_1 = "</span>"
SPACE_MIDDLE_2 = '<span class="space-space">'
SPACE_END = "</span></span>"
SPACE_NL_END = "</span></span><br>"

GLOSSARY_TEMPLATE = """<span class="glossary-term" title="{}">"""

# This should match whitespace_regex in weblate/static/loader-bootstrap.js
WHITESPACE_REGEX = (
    r"(\t|\u00A0|\u00AD|\u1680|\u2000|\u2001|\u2002|\u2003|"
    r"\u2004|\u2005|\u2006|\u2007|\u2008|\u2009|\u200A|"
    r"\u202F|\u205F|\u3000)"
)
WHITESPACE_RE = re.compile(WHITESPACE_REGEX, re.MULTILINE)
NON_BREAKING_SPACES = {"\u00a0", "\u2007", "\u202f"}
NEWLINE_RE = re.compile(r"(\r\n|\r|\n)", re.MULTILINE)
MULTISPACE_RE = re.compile(r"(  +| $|^ )", re.MULTILINE)
ESCAPE_RE = re.compile(r"""['"&<>]""")

SOURCE_LINK = (
    '<a href="{0}" target="_blank" rel="noopener noreferrer"'
    ' class="{2}" dir="ltr" tabindex="-1">{1}</a>'
)
HLCHECK = '<span class="hlcheck" data-value="{}"><span class="highlight-number"></span>'


class Formatter:
    def __init__(
        self,
        idx,
        value,
        unit,
        glossary,
        diff,
        search_match,
        match,
        whitespace: bool = True,
    ) -> None:
        # Inputs
        self.idx = idx
        self.cleaned_value = self.value = value
        self.unit = unit
        self.glossary = glossary
        self.diff = diff
        self.search_match = search_match
        self.match = match
        # Tags output
        self.tags: dict[int, list[str]] = defaultdict(list)
        self.differ = Differ()
        self.whitespace = whitespace

    def insert_before_opening_tags(self, position: int, tag: str) -> None:
        """Insert a tag after closers and before any opening tags at a position."""
        current = self.tags[position]
        insert_at = len(current)
        for index, current_tag in enumerate(current):
            if not current_tag.startswith("</"):
                insert_at = index
                break
        current.insert(insert_at, tag)

    def parse(self) -> None:
        if self.unit:
            self.parse_highlight()
        if self.glossary:
            self.parse_glossary()
        if self.search_match:
            self.parse_search()
        if self.whitespace:
            self.parse_whitespace()
        if self.diff:
            self.parse_diff()

    def parse_diff(self) -> None:  # ruff: ignore[complex-structure]
        """Highlights diff, including extra whitespace."""
        diff = self.differ.compare(self.value, self.diff[self.idx])
        offset = 0
        for op, data in diff:
            if op == self.differ.DIFF_DELETE:
                formatter = Formatter(
                    0,
                    data,
                    self.unit,
                    self.glossary,
                    None,
                    self.search_match,
                    self.match,
                )
                formatter.parse()
                self.tags[offset].append(f"<del>{formatter.format()}</del>")
            elif op == self.differ.DIFF_INSERT:
                end = offset + len(data)
                # Rearrange space highlighting
                move_space = False
                start_space = -1
                start_nl = -1
                append_end = True
                if offset in self.tags:
                    for pos, tag in enumerate(self.tags[offset]):
                        if tag == SPACE_MIDDLE_2:
                            self.tags[offset][pos] = SPACE_MIDDLE_1
                            move_space = True
                            break
                        if tag == SPACE_START:
                            start_space = pos
                            break
                        if tag == SPACE_NL_START:
                            start_nl = pos
                            break

                if start_space != -1:
                    self.tags[offset].insert(start_space, "<ins>")
                    last_middle = None
                    for i in range(len(data)):
                        tagoffset = offset + i + 1
                        if tagoffset not in self.tags:
                            continue
                        for pos, tag in enumerate(self.tags[tagoffset]):
                            if tag == SPACE_END:
                                # Whitespace ends within <ins>
                                start_space = -1
                                break
                            if tag == SPACE_MIDDLE_2:
                                last_middle = (tagoffset, pos)
                        if start_space == -1:
                            break
                    if start_space != -1 and last_middle is not None:
                        self.tags[tagoffset][pos] = SPACE_MIDDLE_1

                elif start_nl != -1:
                    # The line break is always one char wide, so we do not
                    # need the complex logic used for generic whitespace
                    start_tag = self.tags[offset].pop(start_nl)
                    self.tags[end].insert(0, "<ins>")
                    self.tags[end].insert(1, start_tag)
                    self.tags[end].append("</ins>")
                    append_end = False

                else:
                    self.tags[offset].append("<ins>")
                if move_space:
                    self.tags[offset].append(SPACE_START)
                if append_end:
                    self.insert_before_opening_tags(end, "</ins>")
                if start_space != -1:
                    self.tags[end].append(SPACE_START)

                # Rearange other tags
                open_tags = 0
                process = False
                for i in range(offset, end + 1):
                    remove = []
                    for pos, tag in enumerate(self.tags[i]):
                        if not process:
                            if tag.startswith("<ins"):
                                process = True
                            continue
                        if tag.startswith("</ins>"):
                            break
                        if tag.startswith("<span"):
                            open_tags += 1
                        elif tag.startswith("</span"):
                            if open_tags == 0:
                                # Remove tags spanning over <ins>
                                remove.append(pos)
                                found = None
                                for back in range(offset - 1, 0, -1):
                                    for child_pos, child in reversed(
                                        list(enumerate(self.tags[back]))
                                    ):
                                        if child.startswith("<span"):
                                            found = child_pos
                                            break
                                    if found is not None:
                                        del self.tags[back][found]
                                        break
                            else:
                                open_tags -= 1
                    # Remove closing tags (do this outside the loop)
                    for pos in reversed(remove):
                        del self.tags[i][pos]

                offset = end
            elif op == self.differ.DIFF_EQUAL:
                offset += len(data)

    def parse_highlight(self) -> None:
        """Highlights unit placeables."""
        # Importing the check registry here would create a cycle for checks which use
        # Formatter and would make every formatting helper user load all checks.
        from weblate.checks.utils import (  # ruff: ignore[import-outside-top-level]
            highlight_string,
        )

        highlights = highlight_string(self.value, self.unit)
        cleaned_value = list(self.value)
        for highlight in highlights:
            self.tags[highlight.start].append(format_html(HLCHECK, highlight.text))
            self.tags[highlight.end].insert(0, "</span>")
            cleaned_value[highlight.start : highlight.end] = [" "] * (
                highlight.end - highlight.start
            )

        # Prepare cleaned up value for glossary terms (we do not want to extract those
        # from format strings)
        self.cleaned_value = "".join(cleaned_value)

    @staticmethod
    def format_terms(terms):
        forbidden = []
        nontranslatable = []
        translations = []
        for term in terms:
            flags = term.all_flags
            target = html_escape(term.target)
            source = html_escape(term.source)
            # Translators: Glossary term formatting used in a tooltip
            formatted = pgettext("glossary term", "{target} [{source}]").format(
                source=source, target=target
            )
            if "read-only" in flags:
                nontranslatable.append(source)
            elif not target:
                continue
            elif "forbidden" in flags:
                forbidden.append(formatted)
            else:
                translations.append(formatted)

        output = []
        if forbidden:
            output.append(
                "\n".join(
                    (
                        ngettext(
                            "Forbidden translation:",
                            "Forbidden translations:",
                            len(forbidden),
                        ),
                        *forbidden,
                    )
                )
            )
        if nontranslatable:
            output.append(
                "\n".join(
                    (
                        ngettext(
                            "Untranslatable term:",
                            "Untranslatable terms:",
                            len(nontranslatable),
                        ),
                        *nontranslatable,
                    )
                )
            )
        if translations:
            output.append(
                "\n".join(
                    (
                        ngettext(
                            "Glossary term:",
                            "Glossary terms:",
                            len(translations),
                        ),
                        *translations,
                    )
                )
            )
        return "\n\n".join(output)

    def parse_glossary(self) -> None:
        """Highlights glossary entries."""
        # Annotate string with glossary terms
        locations = defaultdict(list)
        for term in self.glossary:
            for start, end in term.glossary_positions:
                # Skip terms whose parts belong to placeholders
                if self.cleaned_value[start:end].lower() != term.source.lower():
                    continue

                for i in range(start, end):
                    locations[i].append(term)
                locations[end].extend([])

        # Render span tags for each glossary term match
        last_entries: list[str] = []
        for position, entries in sorted(locations.items()):
            if last_entries and entries != last_entries:
                self.tags[position].insert(0, "</span>")

            if entries and entries != last_entries:
                self.tags[position].append(
                    GLOSSARY_TEMPLATE.format(self.format_terms(entries))
                )
            last_entries = entries

    def parse_search(self) -> None:
        """Highlights search matches."""
        tag = self.match
        if self.match == "search":
            tag = "hlmatch"

        start_tag = format_html('<span class="{}">', tag)
        end_tag = "</span>"

        for match in re.finditer(
            re.escape(self.search_match), self.value, flags=re.IGNORECASE
        ):
            self.insert_before_opening_tags(match.start(), start_tag)
            self.insert_before_opening_tags(match.end(), end_tag)

    def parse_whitespace(self) -> None:
        """Highlight whitespaces."""
        value = self.value

        for match in NEWLINE_RE.finditer(value):
            self.tags[match.start()].append(SPACE_NL_START)
            self.tags[match.end()].insert(0, SPACE_NL_END)

        for match in MULTISPACE_RE.finditer(value):
            self.tags[match.start()].append(SPACE_START)
            for i in range(match.start() + 1, match.end()):
                self.tags[i].insert(0, SPACE_MIDDLE_1)
                self.tags[i].append(SPACE_MIDDLE_2)
            self.tags[match.end()].insert(0, SPACE_END)

        for match in WHITESPACE_RE.finditer(value):
            whitespace = match.group(0)
            if whitespace == "\t":
                cls = "space-tab"
            elif whitespace in NON_BREAKING_SPACES:
                cls = "space-nbsp"
            else:
                cls = "space-space"
            title = get_display_char(whitespace)[0]
            self.tags[match.start()].append(
                format_html(
                    '<span class="hlspace"><span class="{}" title="{}">', cls, title
                )
            )
            self.tags[match.end()].insert(0, "</span></span>")

    def format_generator(self) -> Generator[str]:
        tags = self.tags
        value = self.value
        current: list[str]
        replacements: dict[int, str] = {}

        # Extract tag positions
        positions: set[int] = set(tags.keys())

        # Avoid processing trailing tags in the loop
        positions.discard(len(value))

        # Replace special characters "&", "<" and ">" to HTML-safe sequences.
        # This is like html.escape but inline
        for match in ESCAPE_RE.finditer(value):
            position = match.start()
            positions.add(position)
            char = match.group()
            if char == "&":
                next_output = "&amp;"
            elif char == "<":
                next_output = "&lt;"
            elif char == ">":
                next_output = "&gt;"
            elif char == '"':
                next_output = "&quot;"
            elif char == "'":
                next_output = "&#x27;"
            else:
                raise ValueError(char)
            replacements[position] = next_output

        previous_start = 0
        for pos in sorted(positions):
            # String up to current position
            yield value[previous_start:pos]

            if pos in tags:
                current = tags[pos]
                # Special case for leading/trailing whitespace char in diff
                if (
                    current
                    and value[pos] == " "
                    and "<ins>" in current
                    and SPACE_START not in current
                ):
                    current.append(SPACE_START)
                    tags[pos + 1].insert(0, SPACE_END)

                elif pos + 1 in tags:
                    next_tags = tags[pos + 1]
                    if (
                        next_tags
                        and value[pos] == " "
                        and "</ins>" in next_tags
                        and SPACE_END not in next_tags
                        and SPACE_MIDDLE_1 not in next_tags
                    ):
                        current.append(SPACE_START)
                        next_tags.insert(0, SPACE_END)

                # Tags
                yield from current

            if pos in replacements:
                # HTML escaped string
                yield replacements[pos]
                previous_start = pos + 1
            else:
                previous_start = pos

        yield value[previous_start:]

        # Trailing tags
        yield from tags[len(value)]

    def format(self):
        # Safe to mark because format_generator escapes raw string content inline
        # and only emits formatter-controlled markup for diffs/highlights/tooltips.
        return mark_safe("".join(self.format_generator()))  # ruff: ignore[suspicious-mark-safe-usage]


def format_unit_target(
    unit,
    *,
    value: str | None = None,
    diff=None,
    search_match: str | None = None,
    match: str = "search",
    simple: bool = False,
    wrap: bool = False,
    show_copy: bool = False,
):
    return format_translation(
        plurals=unit.get_target_plurals() if value is None else split_plural(value),
        language=unit.translation.language,
        plural=unit.translation.plural,
        unit=unit,
        diff=diff,
        search_match=search_match,
        match=match,
        simple=simple,
        wrap=wrap,
        show_copy=show_copy,
    )


def format_unit_source(
    unit,
    *,
    value: str | None = None,
    diff=None,
    search_match: str | None = None,
    match: str = "search",
    simple: bool = False,
    glossary=None,
    wrap: bool = False,
    show_copy: bool = False,
):
    source_translation = unit.translation.component.source_translation
    return format_translation(
        plurals=unit.get_source_plurals() if value is None else split_plural(value),
        language=source_translation.language,
        plural=source_translation.plural,
        unit=unit,
        diff=diff,
        search_match=search_match,
        match=match,
        simple=simple,
        glossary=glossary,
        wrap=wrap,
        show_copy=show_copy,
    )


def format_source_string(
    value: str,
    unit,
    *,
    search_match: str | None = None,
    match: str = "search",
    simple: bool = False,
    glossary=None,
    wrap: bool = False,
    whitespace: bool = True,
):
    """Format simple string as in the unit source language."""
    return format_translation(
        plurals=[value],
        language=unit.translation.component.source_language,
        plural=unit.translation.plural,
        search_match=search_match,
        match=match,
        simple=simple,
        wrap=wrap,
        whitespace=whitespace,
    )


def format_language_string(
    value: str,
    translation,
    *,
    diff=None,
):
    """Format simple string as in the language."""
    return format_translation(
        plurals=split_plural(value),
        language=translation.language,
        plural=translation.plural,
        diff=diff,
    )


def format_translation(
    plurals: list[str],
    language=None,
    *,
    plural=None,
    diff=None,
    search_match: str | None = None,
    simple: bool = False,
    wrap: bool = False,
    unit=None,
    match: str = "search",
    glossary=None,
    whitespace: bool = True,
    show_copy: bool = False,
):
    """Nicely formats translation text possibly handling plurals or diff."""
    is_multivalue = unit is not None and unit.translation.component.is_multivalue

    if plural is None:
        plural = language.plural

    # Split diff plurals
    if diff is not None:
        diff = split_plural(diff)
        # Previous message did not have to be a plural
        while len(diff) < len(plurals):
            diff.append(diff[0])

    # We will collect part for each plural
    parts = []
    has_content = False

    for idx, text in enumerate(plurals):
        formatter = Formatter(
            idx, text, unit, glossary, diff, search_match, match, whitespace=whitespace
        )
        formatter.parse()

        # Show label for plural (if there are any)
        title = ""
        if len(plurals) > 1 and not is_multivalue:
            title = plural.get_plural_name(idx)

        # Join paragraphs
        content = formatter.format()

        parts.append(
            {
                "title": title,
                "content": content,
                "copy": escape(text) if show_copy else "",
            }
        )
        has_content |= bool(content)

    return {
        "simple": simple,
        "wrap": wrap,
        "items": parts,
        "language": language,
        "unit": unit,
        "has_content": has_content,
    }


def unit_state_class(unit) -> str:
    """Return state flags."""
    if unit.has_failing_check:
        return "unit-state-bad"
    if not unit.translated:
        return "unit-state-todo"
    if unit.approved or (unit.readonly and unit.translation.enable_review):
        return "unit-state-approved"
    return "unit-state-translated"


def unit_state_title(unit) -> str:
    state = [unit.get_state_display()]
    checks = unit.active_checks
    if checks:
        state.append(
            f"{pgettext('String state', 'Failing checks:')} {format_html_join_comma('{}', list_to_tuples(checks))}"
        )
    checks = unit.dismissed_checks
    if checks:
        state.append(
            f"{pgettext('String state', 'Dismissed checks:')} {format_html_join_comma('{}', list_to_tuples(checks))}"
        )
    if unit.has_comment:
        state.append(pgettext("String state", "Commented"))
    if unit.has_suggestion:
        state.append(pgettext("String state", "Suggested"))
    if unit.automatically_translated:
        state.append(pgettext("String state", "Automatically translated"))
    if "forbidden" in unit.all_flags:
        state.append(gettext("This translation is forbidden."))
    return "; ".join(state)


def try_linkify_filename(
    text,
    filename: str,
    line: str,
    unit: Unit,
    user: User | None,
    link_class: str = "",
):
    """
    Attempt to convert `text` to a repo link to `filename:line`.

    If the `text` is prefixed with http:// or https://, the
    link will be an absolute link to the specified resource.
    """
    link = None
    if re.search(r"^https?://", text):
        link = text
    elif user:
        link = unit.translation.component.get_repoweb_link(
            filename, line, user.profile.editor_link, user=user
        )
    if link:
        return format_html(SOURCE_LINK, link, text, link_class)
    return text


def get_glossary_badge(component: Component | GhostStats) -> StrOrPromise:
    if isinstance(component, Component) and component.is_glossary:
        return format_html(
            '<span class="badge label-{}">{}</span>',
            component.glossary_color,
            gettext("Glossary"),
        )
    return ""


def get_breadcrumbs(  # ruff: ignore[complex-structure]
    path_object, *, flags: bool = True, only_names: bool = False
) -> Generator[str | tuple[str, str]]:
    def with_url(
        name: Model | int | str, url: str | None = None
    ) -> str | tuple[str, str]:
        if not isinstance(name, str):
            name = str(name)
        if only_names:
            return name
        if url is None:
            url = path_object.get_absolute_url()
        return url, name

    if isinstance(path_object, Unit):
        yield from get_breadcrumbs(
            path_object.translation, flags=flags, only_names=only_names
        )
        yield with_url(path_object.pk)
    elif isinstance(path_object, Translation):
        yield from get_breadcrumbs(
            path_object.component, flags=flags, only_names=only_names
        )
        yield with_url(path_object.language)
    elif isinstance(path_object, Component):
        if path_object.category:
            yield from get_breadcrumbs(
                path_object.category, flags=flags, only_names=only_names
            )
        else:
            yield from get_breadcrumbs(
                path_object.project, flags=flags, only_names=only_names
            )
        name = path_object.name
        if flags:
            name = format_html("{}{}", name, get_glossary_badge(path_object))
        yield with_url(name)
    elif isinstance(path_object, Category):
        if path_object.category:
            yield from get_breadcrumbs(
                path_object.category, flags=flags, only_names=only_names
            )
        else:
            yield from get_breadcrumbs(
                path_object.project, flags=flags, only_names=only_names
            )
        yield with_url(path_object.name)
    elif isinstance(path_object, Project):
        workspace = path_object.workspace
        if workspace is not None:
            yield with_url(workspace.name, workspace.get_absolute_url())
        yield with_url(path_object.name)
    elif isinstance(path_object, Workspace):
        yield with_url(path_object.name)
    elif isinstance(path_object, Language):
        yield with_url(gettext("Languages"), url=reverse("languages"))
        yield with_url(path_object)
    elif isinstance(path_object, ProjectLanguage):
        yield from get_breadcrumbs(
            path_object.project, flags=flags, only_names=only_names
        )
        yield with_url(path_object.language)
    elif isinstance(path_object, CategoryLanguage):
        if path_object.category.category:
            yield from get_breadcrumbs(
                path_object.category.category, flags=flags, only_names=only_names
            )
        else:
            yield from get_breadcrumbs(
                path_object.category.project, flags=flags, only_names=only_names
            )
        yield (
            path_object.category.get_absolute_url(),
            path_object.category.name,
        )
        yield with_url(path_object.language)
    else:
        msg = f"No breadcrumbs for {path_object}"
        raise TypeError(msg)
