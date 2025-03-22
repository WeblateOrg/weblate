# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © WofWca <wofwca@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections import defaultdict
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils.html import conditional_escape, format_html, format_html_join
from django.views.decorators.http import require_POST

from weblate.auth.models import AuthenticatedHttpRequest
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.forms import ReportsForm
from weblate.trans.models import Category, Change, Component, Project
from weblate.trans.util import count_words, redirect_param
from weblate.utils.views import parse_path, show_form_errors

if TYPE_CHECKING:
    from django.db.models import Model
    from django.utils.safestring import SafeString

    from weblate.auth.models import AuthenticatedHttpRequest, User

# Header, three longer fields for name, email and date joined, shorter fields for numbers
RST_HEADING = " ".join(["=" * 40] * 3 + ["=" * 24] * 24)

HTML_HEADING = "<table>\n<tr>{0}</tr>"


def format_plaintext(format_string, *args, **kwargs):
    """
    Format a plain string.

    Same as `format_html` in syntax, but performs no escaping.
    """
    return format_string.format(*args, **kwargs)


def format_plaintext_join(sep, format_string, args_generator):
    """
    Format a plain string with a list.

    Same as `format_html_join` in syntax, but performs no escaping.
    """
    return sep.join(format_plaintext(format_string, *args) for args in args_generator)


def generate_credits(
    user: User,
    start_date,
    end_date,
    language_code: str,
    entity: Project | Component | Category,
    sort_by: str,
    sort_order: str,
):
    """Generate credits data for given component."""
    result = defaultdict(list)

    base = Change.objects.content()
    if user:
        base = base.filter(author=user)

    kwargs: dict[str, Any]
    if entity is None:
        kwargs = {"translation__isnull": False}
    elif isinstance(entity, Project):
        kwargs = {"translation__component__project": entity}
    elif isinstance(entity, Category):
        kwargs = {"translation__component__category": entity}
    else:
        kwargs = {"translation__component": entity}

    languages = Language.objects.filter(**kwargs)
    if language_code:
        languages = languages.filter(code=language_code)

    order_by = "change_count" if sort_by == "count" else "author__date_joined"
    if sort_order == "descending":
        order_by = "-" + order_by

    for *author, language in (
        base.filter(language__in=languages, **kwargs)
        .authors_list(
            (start_date, end_date),
            values_list=("author__date_joined", "language__name"),
        )
        .order_by("language__name", order_by)
    ):
        result[language].append(
            {
                "email": author[0],
                "username": author[1],
                "full_name": author[2],
                "change_count": author[3],
                "date_joined": author[4].isoformat(),
            }
        )

    return [{language: authors} for language, authors in result.items()]


@login_required
@require_POST
def get_credits(request: AuthenticatedHttpRequest, path=None):
    """View for credits."""
    obj = parse_path(request, path, (Component, Category, Project, None))
    scope: dict[str, Model]
    if obj is None:
        scope = {}
    elif isinstance(obj, Project):
        scope = {"project": obj}
    elif isinstance(obj, Category):
        scope = {"category": obj}
    else:
        scope = {"component": obj}

    form = ReportsForm(scope, request.POST)

    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj or "home", "#reports")

    data = generate_credits(
        None if request.user.has_perm("reports.view", obj) else request.user,
        form.cleaned_data["period"]["start_date"],
        form.cleaned_data["period"]["end_date"],
        form.cleaned_data["language"],
        obj,
        form.cleaned_data["sort_by"],
        form.cleaned_data["sort_order"],
    )

    if form.cleaned_data["style"] == "json":
        return JsonResponse(data=data, safe=False)

    if form.cleaned_data["style"] == "html":
        wrap_format = "<table><tbody>{}</tbody></table>"
        language_format = """
        <tr>
            <th>{language}</th>
            <td><ul>{translators}</ul></td>
        </tr>
        """
        translator_format = '<li><a href="mailto:{0}">{2} ({1})</a> - {3}</li>'
        mime = "text/html"
        format_html_or_plain = format_html
        format_html_or_plain_join = format_html_join
    else:
        wrap_format = "{}"
        language_format = "* {language}\n\n{translators}\n"
        translator_format = "    * {2} ({1}) <{0}> - {3}"
        mime = "text/plain"
        format_html_or_plain = format_plaintext
        format_html_or_plain_join = format_plaintext_join

    language_outputs = []
    for language in data:
        name, translators = language.popitem()
        language_outputs.append(
            format_html_or_plain(
                language_format,
                language=name,
                translators=format_html_or_plain_join(
                    "\n",
                    translator_format,
                    (
                        (t["email"], t["username"], t["full_name"], t["change_count"])
                        for t in translators
                    ),
                ),
            )
        )

    body = format_html_or_plain(
        wrap_format,
        format_html_or_plain_join("\n\n", "{}", ((v,) for v in language_outputs)),
    )
    # Just in case someone messes something up.
    # Also consider simply using `html.unescape` instead.
    if mime != "text/plain":
        body = conditional_escape(body)
    return HttpResponse(body, content_type=f"{mime}; charset=utf-8")


COUNT_DEFAULTS = dict.fromkeys(
    (
        "t_chars",
        "t_words",
        "chars",
        "words",
        "edits",
        "count",
        "t_chars_new",
        "t_words_new",
        "chars_new",
        "words_new",
        "edits_new",
        "count_new",
        "t_chars_approve",
        "t_words_approve",
        "chars_approve",
        "words_approve",
        "edits_approve",
        "count_approve",
        "t_chars_edit",
        "t_words_edit",
        "chars_edit",
        "words_edit",
        "edits_edit",
        "count_edit",
    ),
    0,
)


def generate_counts(
    user: User,
    start_date,
    end_date,
    language_code: str,
    sort_by: str,
    sort_order: str,
    **kwargs,
):
    """Generate credits data for given component."""
    result = {}
    action_map = {
        ActionEvents.NEW: "new",
        ActionEvents.APPROVE: "approve",
    }

    base = Change.objects.content().filter(unit__isnull=False)
    base = base.filter(author=user) if user else base.filter(author__isnull=False)
    if language_code:
        base = base.filter(language__code=language_code)

    changes = base.filter(
        timestamp__range=(start_date, end_date), **kwargs
    ).prefetch_related("author", "unit")
    for change in changes:
        email = change.author.email

        if email not in result:
            result[email] = current = {
                "name": change.author.full_name,
                "email": email,
                "date_joined": change.author.date_joined.isoformat(),
            }
            current.update(COUNT_DEFAULTS)
        else:
            current = result[email]

        src_chars = len(change.unit.source)
        src_words = change.unit.num_words
        tgt_chars = len(change.target)
        tgt_words = count_words(change.target, change.language)
        edits = change.get_distance()

        current["chars"] += src_chars
        current["words"] += src_words
        current["t_chars"] += tgt_chars
        current["t_words"] += tgt_words
        current["edits"] += edits
        current["count"] += 1

        suffix = action_map.get(change.action, "edit")

        current["t_chars_" + suffix] += tgt_chars
        current["t_words_" + suffix] += tgt_words
        current["chars_" + suffix] += src_chars
        current["words_" + suffix] += src_words
        current["edits_" + suffix] += edits
        current["count_" + suffix] += 1

    result_list = list(result.values())
    sort_by_key = "count" if sort_by == "count" else "date_joined"
    reverse = sort_order == "descending"
    result_list.sort(key=itemgetter(sort_by_key), reverse=reverse)

    return result_list


@login_required
@require_POST
def get_counts(request: AuthenticatedHttpRequest, path=None):
    """View for work counts."""
    obj = parse_path(request, path, (Component, Category, Project, None))
    kwargs: dict[str, Model]
    if obj is None:
        kwargs = {}
    elif isinstance(obj, Project):
        kwargs = {"project": obj}
    elif isinstance(obj, Category):
        kwargs = {"category": obj}
    else:
        kwargs = {"component": obj}

    form = ReportsForm(kwargs, request.POST)

    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj or "home", "#reports")

    data = generate_counts(
        None if request.user.has_perm("reports.view", obj) else request.user,
        form.cleaned_data["period"]["start_date"],
        form.cleaned_data["period"]["end_date"],
        form.cleaned_data["language"],
        form.cleaned_data["sort_by"],
        form.cleaned_data["sort_order"],
        **kwargs,
    )

    if form.cleaned_data["style"] == "json":
        return JsonResponse(data=data, safe=False)

    headers = (
        "Name",
        "Email",
        "Date joined",
        "Count total",
        "Edits total",
        "Source words total",
        "Source chars total",
        "Target words total",
        "Target chars total",
        "Count new",
        "Edits new",
        "Source words new",
        "Source chars new",
        "Target words new",
        "Target chars new",
        "Count approved",
        "Edits approved",
        "Source words approved",
        "Source chars approved",
        "Target words approved",
        "Target chars approved",
        "Count edited",
        "Edits edited",
        "Source words edited",
        "Source chars edited",
        "Target words edited",
        "Target chars edited",
    )

    start: str | SafeString

    if form.cleaned_data["style"] == "html":
        start = format_html(
            HTML_HEADING,
            format_html_join("", "<th>{}</th>", ((header,) for header in headers)),
        )
        row_start = "<tr>"
        cell_name = cell_count = "<td>{0}</td>\n"
        row_end = "</tr>"
        mime = "text/html"
        end = "</table>"
        format_html_or_plain = format_html
        format_html_or_plain_join = format_html_join
    else:
        start = "{0}\n{1} {2}\n{0}".format(
            RST_HEADING,
            " ".join(f"{h:40}" for h in headers[:3]),
            " ".join(f"{h:24}" for h in headers[3:]),
        )
        row_start = ""
        cell_name = "{0:40} "
        cell_count = "{0:24} "
        row_end = ""
        mime = "text/plain"
        end = RST_HEADING
        format_html_or_plain = format_plaintext
        format_html_or_plain_join = format_plaintext_join

    result = [start]

    for item in data:
        if row_start:
            result.append(row_start)
        result.append(
            format_html_or_plain_join(
                "",
                "{}",
                (
                    (format_html_or_plain(cell_name, item["name"] or "Anonymous"),),
                    (format_html_or_plain(cell_name, item["email"] or ""),),
                    (format_html_or_plain(cell_name, item["date_joined"] or ""),),
                    (format_html_or_plain(cell_count, item["count"]),),
                    (format_html_or_plain(cell_count, item["edits"]),),
                    (format_html_or_plain(cell_count, item["words"]),),
                    (format_html_or_plain(cell_count, item["chars"]),),
                    (format_html_or_plain(cell_count, item["t_words"]),),
                    (format_html_or_plain(cell_count, item["t_chars"]),),
                    (format_html_or_plain(cell_count, item["count_new"]),),
                    (format_html_or_plain(cell_count, item["edits_new"]),),
                    (format_html_or_plain(cell_count, item["words_new"]),),
                    (format_html_or_plain(cell_count, item["chars_new"]),),
                    (format_html_or_plain(cell_count, item["t_words_new"]),),
                    (format_html_or_plain(cell_count, item["t_chars_new"]),),
                    (format_html_or_plain(cell_count, item["count_approve"]),),
                    (format_html_or_plain(cell_count, item["edits_approve"]),),
                    (format_html_or_plain(cell_count, item["words_approve"]),),
                    (format_html_or_plain(cell_count, item["chars_approve"]),),
                    (format_html_or_plain(cell_count, item["t_words_approve"]),),
                    (format_html_or_plain(cell_count, item["t_chars_approve"]),),
                    (format_html_or_plain(cell_count, item["count_edit"]),),
                    (format_html_or_plain(cell_count, item["edits_edit"]),),
                    (format_html_or_plain(cell_count, item["words_edit"]),),
                    (format_html_or_plain(cell_count, item["chars_edit"]),),
                    (format_html_or_plain(cell_count, item["t_words_edit"]),),
                    (format_html_or_plain(cell_count, item["t_chars_edit"]),),
                ),
            )
        )
        if row_end:
            result.append(row_end)

    result.append(end)

    return HttpResponse("\n".join(result), content_type=f"{mime}; charset=utf-8")
