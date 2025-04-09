# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime
from html import escape as html_escape
from typing import TYPE_CHECKING

from django import forms, template
from django.contrib.humanize.templatetags.humanize import intcomma
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import number_format as django_number_format
from django.utils.html import escape, format_html, format_html_join, urlize
from django.utils.safestring import SafeString, mark_safe
from django.utils.translation import gettext, gettext_lazy, ngettext, pgettext
from siphashc import siphash

from weblate.accounts.avatar import get_user_display
from weblate.accounts.models import Profile
from weblate.auth.models import User
from weblate.checks.models import CHECKS
from weblate.checks.utils import highlight_string
from weblate.lang.models import Language
from weblate.trans.filter import FILTERS, get_filter_choice
from weblate.trans.forms import FieldDocsMixin
from weblate.trans.models import (
    Announcement,
    Category,
    Component,
    ComponentList,
    ContributorAgreement,
    Project,
    Translation,
    Unit,
)
from weblate.trans.models.translation import GhostTranslation
from weblate.trans.specialchars import get_display_char
from weblate.trans.util import split_plural, translation_percent
from weblate.utils.diff import Differ
from weblate.utils.docs import get_doc_url
from weblate.utils.hash import hash_to_checksum
from weblate.utils.html import format_html_join_comma, list_to_tuples
from weblate.utils.markdown import render_markdown
from weblate.utils.messages import get_message_kind as get_message_kind_impl
from weblate.utils.random import get_random_identifier
from weblate.utils.stats import (
    BaseStats,
    CategoryLanguage,
    GhostProjectLanguageStats,
    GhostStats,
    ProjectLanguage,
)
from weblate.utils.templatetags.icons import icon
from weblate.utils.views import SORT_CHOICES

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

    from django.db.models import QuerySet
    from django.template.context import Context
    from django_stubs_ext import StrOrPromise

    from weblate.metrics.wrapper import MetricsWrapper

register = template.Library()

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
NEWLINE_RE = re.compile(r"(\r\n|\r|\n)", re.MULTILINE)
MULTISPACE_RE = re.compile(r"(  +| $|^ )", re.MULTILINE)
ESCAPE_RE = re.compile(r"""['"&<>]""")
TYPE_MAPPING = {True: "yes", False: "no", None: "unknown"}
# Mapping of status report flags to names
NAME_MAPPING = {
    True: gettext_lazy("Good configuration"),
    False: gettext_lazy("Bad configuration"),
    None: gettext_lazy("Possible configuration"),
}

FLAG_TEMPLATE = '<span title="{0}" class="{1}">{2}</span>'

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

    def parse_diff(self) -> None:  # noqa: C901
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
                if offset in self.tags:
                    for pos, tag in enumerate(self.tags[offset]):
                        if tag == SPACE_MIDDLE_2:
                            self.tags[offset][pos] = SPACE_MIDDLE_1
                            move_space = True
                            break
                        if tag == SPACE_START:
                            start_space = pos
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

                else:
                    self.tags[offset].append("<ins>")
                if move_space:
                    self.tags[offset].append(SPACE_START)
                self.tags[end].append("</ins>")
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
        highlights = highlight_string(self.value, self.unit)
        cleaned_value = list(self.value)
        for start, end, content in highlights:
            self.tags[start].append(format_html(HLCHECK, content))
            self.tags[end].insert(0, "</span>")
            cleaned_value[start:end] = [" "] * (end - start)

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
            self.tags[match.start()].append(start_tag)
            self.tags[match.end()].insert(0, end_tag)

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
            cls = "space-tab" if whitespace == "\t" else "space-space"
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
        return mark_safe("".join(self.format_generator()))  # noqa: S308


@register.inclusion_tag("snippets/format-translation.html")
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


@register.inclusion_tag("snippets/format-translation.html")
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


@register.inclusion_tag("snippets/format-translation.html")
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


@register.inclusion_tag("snippets/format-translation.html")
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


@register.simple_tag
def search_name(query):
    """Return name for a query string."""
    return FILTERS.get_search_name(query)


@register.simple_tag
def check_name(check):
    """Return check name, or its id if check is not known."""
    try:
        return escape(CHECKS[check].name)
    except KeyError:
        return escape(check)


@register.simple_tag
def check_description(check):
    """Return check description, or its id if check is not known."""
    try:
        return escape(CHECKS[check].description)
    except KeyError:
        return escape(check)


@register.simple_tag(takes_context=True)
def documentation(context: Context, page, anchor=""):
    """Return link to Weblate documentation."""
    # User might not be present on error pages
    user = context.get("user")
    # Use object method get_doc_url if present
    if hasattr(page, "get_doc_url"):
        return page.get_doc_url(user=user)
    return get_doc_url(page, anchor, user=user)


def render_documentation_icon(doc_url: str, *, right: bool = False):
    if not doc_url:
        return ""
    return format_html(
        """<a class="{} doc-link" href="{}" title="{}" target="_blank" rel="noopener" tabindex="-1">{}</a>""",
        "pull-right flip" if right else "",
        doc_url,
        gettext("Documentation"),
        icon("info.svg"),
    )


@register.simple_tag(takes_context=True)
def documentation_icon(
    context: Context, page: str, anchor: str = "", right: bool = False
):
    return render_documentation_icon(documentation(context, page, anchor), right=right)


@register.simple_tag(takes_context=True)
def form_field_doc_link(context: Context, form: forms.Form, field: forms.Field) -> str:
    if isinstance(form, FieldDocsMixin) and (field_doc := form.get_field_doc(field)):
        return render_documentation_icon(get_doc_url(*field_doc, user=context["user"]))
    return ""


@register.inclusion_tag("message.html")
def show_message(tags, message):
    tags = tags.split()
    final = []
    task_id = None
    for tag in tags:
        if tag.startswith("task:"):
            task_id = tag[5:]
        else:
            final.append(tag)
    return {"tags": " ".join(final), "task_id": task_id, "message": message}


def naturaltime_past(value, now):
    """Convert past dates to natural time."""
    delta = now - value

    if delta.days >= 365:
        count = delta.days // 365
        if count == 1:
            return gettext("a year ago")
        return ngettext("%(count)s year ago", "%(count)s years ago", count) % {
            "count": count
        }
    if delta.days >= 30:
        count = delta.days // 30
        if count == 1:
            return gettext("a month ago")
        return ngettext("%(count)s month ago", "%(count)s months ago", count) % {
            "count": count
        }
    if delta.days >= 14:
        count = delta.days // 7
        return ngettext("%(count)s week ago", "%(count)s weeks ago", count) % {
            "count": count
        }
    if delta.days > 0:
        if delta.days == 7:
            return gettext("a week ago")
        if delta.days == 1:
            return gettext("yesterday")
        return ngettext("%(count)s day ago", "%(count)s days ago", delta.days) % {
            "count": delta.days
        }
    if delta.seconds == 0:
        return gettext("now")
    if delta.seconds < 60:
        if delta.seconds == 1:
            return gettext("a second ago")
        return ngettext(
            "%(count)s second ago", "%(count)s seconds ago", delta.seconds
        ) % {"count": delta.seconds}
    if delta.seconds // 60 < 60:
        count = delta.seconds // 60
        if count == 1:
            return gettext("a minute ago")
        return ngettext("%(count)s minute ago", "%(count)s minutes ago", count) % {
            "count": count
        }
    count = delta.seconds // 60 // 60
    if count == 1:
        return gettext("an hour ago")
    return ngettext("%(count)s hour ago", "%(count)s hours ago", count) % {
        "count": count
    }


def naturaltime_future(value, now):
    """Convert future dates to natural time."""
    delta = value - now

    if delta.days >= 365:
        count = delta.days // 365
        if count == 1:
            return gettext("a year from now")
        return ngettext(
            "%(count)s year from now", "%(count)s years from now", count
        ) % {"count": count}
    if delta.days >= 30:
        count = delta.days // 30
        if count == 1:
            return gettext("a month from now")
        return ngettext(
            "%(count)s month from now", "%(count)s months from now", count
        ) % {"count": count}
    if delta.days >= 14:
        count = delta.days // 7
        return ngettext(
            "%(count)s week from now", "%(count)s weeks from now", count
        ) % {"count": count}
    if delta.days > 0:
        if delta.days == 1:
            return gettext("tomorrow")
        if delta.days == 7:
            return gettext("a week from now")
        return ngettext(
            "%(count)s day from now", "%(count)s days from now", delta.days
        ) % {"count": delta.days}
    if delta.seconds == 0:
        return gettext("now")
    if delta.seconds < 60:
        if delta.seconds == 1:
            return gettext("a second from now")
        return ngettext(
            "%(count)s second from now", "%(count)s seconds from now", delta.seconds
        ) % {"count": delta.seconds}
    if delta.seconds // 60 < 60:
        count = delta.seconds // 60
        if count == 1:
            return gettext("a minute from now")
        return ngettext(
            "%(count)s minute from now", "%(count)s minutes from now", count
        ) % {"count": count}
    count = delta.seconds // 60 // 60
    if count == 1:
        return gettext("an hour from now")
    return ngettext("%(count)s hour from now", "%(count)s hours from now", count) % {
        "count": count
    }


@register.filter(is_safe=True)
def naturaltime(
    value: float | datetime, microseconds: bool = False, *, now: datetime | None = None
):
    """
    Heavily based on Django's django.contrib.humanize implementation of naturaltime.

    For date and time values shows how many seconds, minutes or hours ago compared to
    current timestamp returns representing string.
    """
    # float is what time() returns
    if isinstance(value, float):
        value = datetime.fromtimestamp(value, tz=timezone.get_current_timezone())
    # datetime is a subclass of date
    if not isinstance(value, date):
        return value

    # Default to current timestamp
    if now is None:
        now = timezone.now()

    if value < now:
        text = naturaltime_past(value, now)
    else:
        text = naturaltime_future(value, now)

    # Strip microseconds
    if isinstance(value, datetime) and not microseconds:
        value = value.replace(microsecond=0)

    return format_html(
        '<span title="{}">{}</span>',
        timezone.localtime(value).isoformat(),
        text,
    )


def get_stats(obj):
    if isinstance(obj, BaseStats):
        return obj
    return obj.stats


@register.simple_tag
def review_percent(obj):
    stats = get_stats(obj)
    return list_objects_percent(
        value=stats.approved + stats.readonly,
        percent=stats.approved_percent + stats.readonly_percent,
        query="q=state:>=approved",
        total=stats.all,
        checks=stats.allchecks,
        css="zero-width-540",
    )


def translation_progress_render(
    total: int, readonly: int, approved: int, translated: int, has_review: bool
) -> StrOrPromise:
    if has_review:
        translated -= approved
        approved += readonly
        translated -= readonly

    approved_percent = translation_percent(approved, total, False)
    good_percent = translation_percent(translated, total)

    approved_tag = ""
    good_tag = ""
    if approved_percent > 0.1:
        approved_tag = format_html(
            """
            <div class="progress-bar"
                role="progressbar"
                aria-valuenow="{approved}"
                aria-valuemin="0"
                aria-valuemax="100"
                style="width: {approved}%"
                title="{title}"></div>
            """,
            approved=f"{approved_percent:.1f}",
            title=gettext("Approved"),
        )
    if good_percent > 0.1:
        good_tag = format_html(
            """
            <div class="progress-bar progress-bar-success"
                role="progressbar"
                aria-valuenow="{good}"
                aria-valuemin="0"
                aria-valuemax="100"
                style="width: {good}%"
                title="{title}"></div>
            """,
            good=f"{good_percent:.1f}",
            title=gettext("Translated without any problems"),
        )

    return format_html(
        """<div class="progress" title="{}">{}{}</div>""",
        gettext("Needs attention"),
        approved_tag,
        good_tag,
    )


@register.simple_tag
def translation_progress(obj):
    stats = get_stats(obj)
    return translation_progress_render(
        stats.all,
        stats.readonly,
        stats.approved,
        stats.translated_without_checks,
        stats.has_review,
    )


@register.simple_tag
def words_progress(obj):
    stats = get_stats(obj)
    return translation_progress_render(
        stats.all_words,
        stats.readonly_words,
        stats.approved_words,
        stats.translated_without_checks_words,
        stats.has_review,
    )


@register.simple_tag
def chars_progress(obj):
    stats = get_stats(obj)
    return translation_progress_render(
        stats.all_chars,
        stats.readonly_chars,
        stats.approved_chars,
        stats.translated_without_checks_chars,
        stats.has_review,
    )


@register.simple_tag
def unit_state_class(unit) -> str:
    """Return state flags."""
    if unit.has_failing_check:
        return "unit-state-bad"
    if not unit.translated:
        return "unit-state-todo"
    if unit.approved or (unit.readonly and unit.translation.enable_review):
        return "unit-state-approved"
    return "unit-state-translated"


@register.simple_tag
def unit_state_title(unit) -> str:
    state = [unit.get_state_display()]
    checks = unit.active_checks
    if checks:
        state.append(
            "{} {}".format(
                pgettext("String state", "Failing checks:"),
                format_html_join_comma(
                    "{}",
                    list_to_tuples(checks),
                ),
            )
        )
    checks = unit.dismissed_checks
    if checks:
        state.append(
            "{} {}".format(
                pgettext("String state", "Dismissed checks:"),
                format_html_join_comma("{}", list_to_tuples(checks)),
            )
        )
    if unit.has_comment:
        state.append(pgettext("String state", "Commented"))
    if unit.has_suggestion:
        state.append(pgettext("String state", "Suggested"))
    if "forbidden" in unit.all_flags:
        state.append(gettext("This translation is forbidden."))
    return "; ".join(state)


def try_linkify_filename(
    text, filename: str, line: str, unit, profile, link_class: str = ""
):
    """
    Attempt to convert `text` to a repo link to `filename:line`.

    If the `text` is prefixed with http:// or https://, the
    link will be an absolute link to the specified resource.
    """
    link = None
    if re.search(r"^https?://", text):
        link = text
    elif profile:
        link = unit.translation.component.get_repoweb_link(
            filename, line, profile.editor_link
        )
    if link:
        return format_html(SOURCE_LINK, link, text, link_class)
    return text


@register.simple_tag
def get_location_links(user: User | None, unit):
    """Generate links to source files where translation was used."""
    # Fallback to source unit if it has more information
    if not unit.location and unit.source_unit.location:
        unit = unit.source_unit

    # Do we have any locations?
    if not unit.location:
        return ""

    # Is it just an ID?
    if unit.location.isdigit():
        return gettext("string ID %s") % unit.location

    profile = user.profile if user else None

    # Go through all locations separated by comma
    return format_html_join(
        mark_safe('\n<span class="divisor">•</span>\n'),
        "{}",
        (
            (
                try_linkify_filename(
                    location, filename, line, unit, profile, "wrap-text"
                ),
            )
            for location, filename, line in unit.get_locations()
        ),
    )


@register.simple_tag(takes_context=True)
def announcements(context: Context, project=None, component=None, language=None):
    """Display announcement messages for given context."""
    user = context["user"]

    return format_html_join(
        "\n",
        "{}",
        (
            (
                render_to_string(
                    "message.html",
                    {
                        "tags": f"{announcement.severity} announcement",
                        "message": render_markdown(announcement.message),
                        "announcement": announcement,
                        "can_delete": user.has_perm(
                            "announcement.delete", announcement
                        ),
                    },
                ),
            )
            for announcement in Announcement.objects.context_filter(
                project, component, language
            )
        ),
    )


@register.simple_tag(takes_context=True)
def active_tab(context: Context, slug):
    active = "active" if slug == context["active_tab_slug"] else ""
    return format_html('class="tab-pane {}" id="{}"', active, slug)


@register.simple_tag(takes_context=True)
def active_link(context: Context, slug):
    if slug == context["active_tab_slug"]:
        return mark_safe('class="active"')
    return ""


def _needs_agreement(component, user: User) -> bool:
    if not component.agreement:
        return False
    return not ContributorAgreement.objects.has_agreed(user, component)


@register.simple_tag(takes_context=True)
def needs_agreement(context: Context, component):
    return _needs_agreement(component, context["user"])


@register.simple_tag(takes_context=True)
def show_contributor_agreement(context: Context, component):
    if not _needs_agreement(component, context["user"]):
        return ""

    return render_to_string(
        "snippets/component/contributor-agreement.html",
        {
            "object": component,
            "next": context["request"].get_full_path(),
            "user": context["user"],
        },
    )


@register.simple_tag(takes_context=True)
def get_translate_url(context: Context, obj, glossary_browse=True) -> str:
    """Get translate URL based on user preference."""
    if isinstance(obj, BaseStats) or not hasattr(obj, "get_translate_url"):
        return ""
    if glossary_browse and hasattr(obj, "component") and obj.component.is_glossary:
        name = "browse"
    elif context["user"].profile.translate_mode == Profile.TRANSLATE_ZEN:
        name = "zen"
    else:
        name = "translate"
    return reverse(name, kwargs={"path": obj.get_url_path()})


@register.simple_tag
def get_search_url(obj) -> str:
    """Get translate URL based on user preference."""
    if not hasattr(obj, "get_url_path"):
        # Ghost translation
        return ""
    return reverse("search", kwargs={"path": obj.get_url_path()})


@register.simple_tag(takes_context=True)
def get_browse_url(context: Context, obj):
    """Get translate URL based on user preference."""
    # Project listing on language page
    if "language" in context and isinstance(obj, Project):
        project_language = ProjectLanguage(obj, context["language"])
        return project_language.get_absolute_url()

    return obj.get_absolute_url()


@register.simple_tag(takes_context=True)
def init_unique_row_id(context) -> str:
    context["row_uuid"] = get_random_identifier()
    return ""


@register.simple_tag(takes_context=True)
def get_unique_row_id(context: Context, obj):
    """Get unique row ID for multiline tables."""
    return "{}-{}".format(context["row_uuid"], obj.pk)


@register.simple_tag
def get_filter_name(name: str) -> str:
    names = dict(get_filter_choice())
    return names[name]


def translation_alerts(
    translation: Translation | ProjectLanguage | GhostTranslation,
) -> Iterable[tuple[str, StrOrPromise, str | None]]:
    if translation.is_source:
        yield (
            "state/source.svg",
            gettext("This language is used for source strings."),
            None,
        )


def component_alerts(
    component: Component,
) -> Iterable[tuple[str, StrOrPromise, str | None]]:
    if component.is_repo_link:
        yield (
            "state/link.svg",
            gettext("This component is linked to the %(target)s repository.")
            % {"target": component.linked_component},
            None,
        )

    if component.all_active_alerts:
        yield (
            "state/alert.svg",
            gettext("Fix this component to clear its alerts."),
            component.get_absolute_url() + "#alerts",
        )

    if component.locked:
        yield ("state/lock.svg", gettext("This translation is locked."), None)

    if component.in_progress():
        yield (
            "state/update.svg",
            gettext("Updating translation component…"),
            reverse("show_progress", kwargs={"path": component.get_url_path()})
            + "?info=1",
        )


def project_alerts(project: Project) -> Iterable[tuple[str, StrOrPromise, str | None]]:
    if project.has_alerts:
        yield (
            "state/alert.svg",
            gettext("Some of the components within this project have alerts."),
            None,
        )

    if project.locked:
        yield ("state/lock.svg", gettext("This translation is locked."), None)


def get_alerts(
    *,
    context: Context,
    obj: Translation
    | Component
    | ProjectLanguage
    | Project
    | GhostProjectLanguageStats,
    translation: Translation | GhostTranslation | None,
    component: Component | None,
    project: Project | None,
    project_language: ProjectLanguage | None,
) -> Iterable[tuple[str, StrOrPromise, str | None]]:
    global_base = context.get("global_base")

    if project_language is not None:
        # For source language
        yield from translation_alerts(project_language)

    if project is not None and context["user"].has_perm("project.edit", project):
        yield ("state/admin.svg", gettext("You administrate this project."), None)

    if translation is not None:
        yield from translation_alerts(translation)

    if component is not None:
        yield from (component_alerts(component))
    elif project is not None:
        yield from (project_alerts(project))

    if getattr(obj, "is_ghost", False):
        yield (
            ("state/ghost.svg", gettext("This translation does not yet exist."), None)
        )
    elif global_base:
        if isinstance(global_base, str):
            global_base = getattr(obj, global_base)
        stats = get_stats(obj)

        count = global_base.source_strings - stats.all
        if count:
            yield (
                (
                    "state/ghost.svg",
                    ngettext(
                        "%(count)s string is not being translated here.",
                        "%(count)s strings are not being translated here.",
                        count,
                    )
                    % {"count": intcomma(count)},
                    None,
                )
            )

    if is_shared := getattr(obj, "is_shared", False):
        yield (
            (
                "state/share.svg",
                gettext("Shared from the %s project.") % is_shared,
                None,
            )
        )


@register.simple_tag(takes_context=True)
def indicate_alerts(
    context: Context,
    obj: Translation
    | Component
    | ProjectLanguage
    | Project
    | GhostProjectLanguageStats,
):
    translation: Translation | GhostTranslation | None = None
    component: Component | None = None
    project: Project | None = None
    project_language: ProjectLanguage | None = None

    if isinstance(obj, Translation | GhostTranslation):
        translation = obj
        component = obj.component
        project = component.project
    elif isinstance(obj, Component):
        component = obj
        project = component.project
    elif isinstance(obj, Project):
        project = obj
    elif isinstance(obj, ProjectLanguage):
        project = obj.project
        project_language = obj
    elif isinstance(obj, GhostProjectLanguageStats):
        component = obj.component
        project = component.project

    icons = format_html_join(
        "\n",
        '{}<span class="state-icon {}" title="{}" alt="{}">{}</span>{}',
        (
            (
                format_html('<a href="{}">', url) if url else "",
                "grey"
                if icon_name == "state/ghost.svg"
                else "red"
                if icon_name == "state/alert.svg"
                else "",
                text,
                text,
                icon(icon_name),
                mark_safe("</a>") if url else "",
            )
            for icon_name, text, url in get_alerts(
                context=context,
                translation=translation,
                component=component,
                project=project,
                project_language=project_language,
                obj=obj,
            )
        ),
    )

    license_badge = ""
    if component and component.license and component.license != "proprietary":
        license_badge = format_html(
            ' <span title="{}" class="license badge">{}</span>',
            component.get_license_display(),
            component.license,
        )

    return format_html("{}{}", icons, license_badge)


@register.filter(is_safe=True)
def markdown(text):
    return format_html('<div class="markdown">{}</div>', render_markdown(text))


@register.filter
def choiceval(boundfield):
    """
    Get literal value from a field's choices.

    Empty value is returned if value is not selected or invalid.
    """
    value = boundfield.value()
    if value is None:
        return ""
    if value is True:
        return gettext("enabled")
    if not hasattr(boundfield.field, "choices"):
        return value
    choices = {str(choice): value for choice, value in boundfield.field.choices}
    if isinstance(value, list):
        return format_html_join_comma(
            "{}", list_to_tuples(choices.get(val, val) for val in value)
        )
    return choices.get(value, value)


@register.filter
def format_commit_author(commit):
    users = User.objects.filter(
        social_auth__verifiedemail__email=commit["author_email"]
    )
    user = users.first()
    if user is None:
        return commit["author_name"]
    return get_user_display(user, True, True)


@register.filter
def percent_format(number):
    if number < 0.1:
        percent = 0
    elif number < 1:
        percent = 1
    elif number >= 99.999999:
        percent = 100
    elif number > 99:
        percent = 99
    else:
        percent = int(number)
    return mark_safe(  # noqa: S308
        pgettext("Translated percents", "%(percent)s%%")
        % {"percent": intcomma(percent)}
    )


@register.filter
def number_format(number):
    format_string = "%s"
    if number > 99999999:
        number //= 1000000
        # Translators: Number format, in millions (mega)
        format_string = gettext("%s M")
    elif number > 99999:
        number //= 1000
        # Translators: Number format, in thousands (kilo)
        format_string = gettext("%s k")
    return format_string % django_number_format(number, force_grouping=True)


@register.filter
def trend_format(number):
    if number < 0:
        prefix = "−"
        trend = "trend-down"
    else:
        prefix = "+"
        trend = "trend-up"
    number = abs(number)
    if number < 0.1:
        return "—"
    return format_html(
        '{}{} <span class="{}"></span>',
        prefix,
        percent_format(number),
        trend,
    )


@register.filter
def hash_text(name):
    """Hash text for use in HTML id."""
    return hash_to_checksum(siphash("Weblate URL hash", name.encode()))


@register.simple_tag
def sort_choices():
    return SORT_CHOICES.items()


@register.simple_tag(takes_context=True)
def render_alert(context: Context, alert):
    return alert.render(user=context["user"])


@register.simple_tag
def get_message_kind(tags):
    return get_message_kind_impl(tags)


@register.simple_tag
def any_unit_has_context(units: Iterable[Unit]):
    return any(unit.context for unit in units)


@register.filter(is_safe=True, needs_autoescape=True)
def urlize_ugc(value, autoescape=True):
    """Convert URLs in plain text into clickable links."""
    html = urlize(value, nofollow=True, autoescape=autoescape)
    return mark_safe(  # noqa: S308
        html.replace('rel="nofollow"', 'rel="ugc" target="_blank"')
    )


@register.simple_tag
def get_glossary_badge(component: Component | GhostStats) -> StrOrPromise:
    if isinstance(component, Component) and component.is_glossary:
        return format_html(
            '<span class="label label-{}">{}</span>',
            component.glossary_color,
            gettext("Glossary"),
        )
    return ""


def get_breadcrumbs(path_object, flags: bool = True):
    if isinstance(path_object, Unit):
        yield from get_breadcrumbs(path_object.translation)
        yield path_object.get_absolute_url(), path_object.pk
    elif isinstance(path_object, Translation):
        yield from get_breadcrumbs(path_object.component)
        yield path_object.get_absolute_url(), path_object.language
    elif isinstance(path_object, Component):
        if path_object.category:
            yield from get_breadcrumbs(path_object.category)
        else:
            yield from get_breadcrumbs(path_object.project)
        name = path_object.name
        if flags:
            name = format_html("{}{}", name, get_glossary_badge(path_object))
        yield path_object.get_absolute_url(), name
    elif isinstance(path_object, Category):
        if path_object.category:
            yield from get_breadcrumbs(path_object.category)
        else:
            yield from get_breadcrumbs(path_object.project)
        yield path_object.get_absolute_url(), path_object.name
    elif isinstance(path_object, Project):
        yield path_object.get_absolute_url(), path_object.name
    elif isinstance(path_object, Language):
        yield reverse("languages"), gettext("Languages")
        yield path_object.get_absolute_url(), path_object
    elif isinstance(path_object, ProjectLanguage):
        yield (
            f"{path_object.project.get_absolute_url()}#languages",
            path_object.project.name,
        )
        yield path_object.get_absolute_url(), path_object.language
    elif isinstance(path_object, CategoryLanguage):
        if path_object.category.category:
            yield from get_breadcrumbs(path_object.category.category)
        else:
            yield from get_breadcrumbs(path_object.category.project)
        yield (
            f"{path_object.category.get_absolute_url()}#languages",
            path_object.category.name,
        )
        yield path_object.get_absolute_url(), path_object.language
    else:
        msg = f"No breadcrumbs for {path_object}"
        raise TypeError(msg)


@register.simple_tag
def path_object_breadcrumbs(path_object, flags: bool = True):
    return format_html_join(
        "\n", '<li><a href="{}">{}</a></li>', get_breadcrumbs(path_object, flags)
    )


@register.simple_tag
def get_projectlanguage(project, language):
    return ProjectLanguage(project=project, language=language)


@register.simple_tag
def get_workflow_flags(translation, component):
    if translation:
        return {
            "suggestion_voting": translation.suggestion_voting,
            "suggestion_autoaccept": translation.suggestion_autoaccept,
            "enable_suggestions": translation.enable_suggestions,
            "translation_review": translation.enable_review,
        }
    return {
        "suggestion_voting": component.suggestion_voting,
        "suggestion_autoaccept": component.suggestion_autoaccept,
        "enable_suggestions": component.enable_suggestions,
        "translation_review": component.project.translation_review,
    }


@register.simple_tag
def list_objects_number(
    value: int,
    search_url: str | None = None,
    translate_url: str | None = None,
    query: str = "",
    css: str | None = None,
    show_zero: bool = False,
):
    value_formatted: str | SafeString
    url_start: str | SafeString
    url_end: str | SafeString
    url_start = url_end = ""
    if value == 0 and not show_zero:
        value_formatted = format_html("""<span class="sr-only">{}</span>""", value)
    else:
        if search_url or translate_url:
            url_start = format_html(
                '<a href="{url}?{query}">',
                url=translate_url or search_url,
                query=query,
            )
            url_end = mark_safe("</a>")
        value_formatted = intcomma(value)
    return format_html(
        """
        <td class="number {css}" data-value="{value}">
            {url_start}
            {value_formatted}
            {url_end}
        </td>
        """,
        url_start=url_start,
        url_end=url_end,
        css=css if css is not None else "",
        value=value,
        value_formatted=value_formatted,
    )


@register.simple_tag
def list_objects_percent(
    percent: float,
    value: int,
    total: int,
    checks: int,
    search_url: str | None = None,
    translate_url: str | None = None,
    query: str = "",
    css: str | None = None,
):
    url_start: str | SafeString
    url_end: str | SafeString
    if search_url or translate_url:
        url_start = format_html(
            '<a href="{url}?{query}">',
            url=translate_url or search_url,
            query=query,
        )
        url_end = mark_safe("</a>")
    else:
        url_start = url_end = ""

    if value and value == total and checks == 0:
        percent_formatted = format_html(
            """<span class="green" title="{}">{}</span>""",
            ngettext(
                "Completed translation with %(count)s string",
                "Completed translation with %(count)s strings",
                total,
            )
            % {"count": intcomma(total)},
            icon("check.svg"),
        )
    elif value == 0 and total == 0:
        percent_formatted = format_html(
            """<span class="green" title="{}">{}</span>""",
            gettext("No strings to translate"),
            icon("check.svg"),
        )
    else:
        percent_formatted = percent_format(percent)
    return format_html(
        """
        <td class="number {css}" data-value="{percent}" title="{value_formatted}">
            {url_start}
            {percent_formatted}
            {url_end}
        </td>
        """,
        url_start=url_start,
        url_end=url_end,
        css=css,
        percent=f"{percent:f}",
        percent_formatted=percent_formatted,
        value_formatted=gettext("%(value)s of %(all)s")
        % {"value": intcomma(value), "all": intcomma(total)},
    )


@register.inclusion_tag("snippets/info.html", takes_context=True)
def show_info(  # noqa: PLR0913
    context: Context,
    *,
    project: Project | None = None,
    component: Component | None = None,
    translation: Translation | None = None,
    language: Language | None = None,
    componentlist: ComponentList | None = None,
    stats: BaseStats | None = None,
    metrics: MetricsWrapper | None = None,
    show_source: bool = False,
    show_global: bool = False,
    show_full_language: bool = True,
    top_users: QuerySet[Profile] | None = None,
    total_translations: int | None = None,
):
    """
    Render project information table.

    This merely exists to be able to pass default values to {% include %}.
    """
    return {
        "user": context["user"],
        "project": project,
        "component": component,
        "translation": translation,
        "language": language,
        "componentlist": componentlist,
        "stats": stats,
        "metrics": metrics,
        "show_source": show_source,
        "show_global": show_global,
        "show_full_language": show_full_language,
        "top_users": top_users,
        "total_translations": total_translations,
    }
