#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
# Copyright © 2022 WofWca <wofwca@protonmail.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils.html import conditional_escape, format_html, format_html_join
from django.views.decorators.http import require_POST

from weblate.lang.models import Language
from weblate.trans.forms import ReportsForm
from weblate.trans.models.change import Change
from weblate.trans.util import redirect_param
from weblate.utils.views import get_component, get_project, show_form_errors

# Header, two longer fields for name and email, shorter fields for numbers
RST_HEADING = " ".join(["=" * 40] * 2 + ["=" * 24] * 20)

HTML_HEADING = "<table>\n<tr>{0}</tr>"


def format_plaintext(format_string, *args, **kwargs):
    """Same as `format_html` in syntax, but performs no escaping."""
    return format_string.format(*args, **kwargs)


def format_plaintext_join(sep, format_string, args_generator):
    """Same as `format_html_join` in syntax, but performs no escaping."""
    return sep.join(format_plaintext(format_string, *args) for args in args_generator)


def generate_credits(user, start_date, end_date, **kwargs):
    """Generate credits data for given component."""
    result = []

    base = Change.objects.content()
    if user:
        base = base.filter(author=user)

    for language in Language.objects.filter(**kwargs).distinct().iterator():
        authors = base.filter(language=language, **kwargs).authors_list(
            (start_date, end_date)
        )
        if not authors:
            continue
        result.append({language.name: sorted(authors, key=lambda item: item[2])})

    return result


@login_required
@require_POST
def get_credits(request, project=None, component=None):
    """View for credits."""
    if project is None:
        obj = None
        kwargs = {"translation__isnull": False}
    elif component is None:
        obj = get_project(request, project)
        kwargs = {"translation__component__project": obj}
    else:
        obj = get_component(request, project, component)
        kwargs = {"translation__component": obj}

    form = ReportsForm(request.POST)

    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj or "home", "#reports")

    data = generate_credits(
        None if request.user.has_perm("reports.view", obj) else request.user,
        form.cleaned_data["start_date"],
        form.cleaned_data["end_date"],
        **kwargs,
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
        translator_format = '<li><a href="mailto:{0}">{1}</a> ({2})</li>'
        mime = "text/html"
        format_html_or_plain = format_html
        format_html_or_plain_join = format_html_join
    else:
        wrap_format = "{}"
        language_format = "* {language}\n\n{translators}\n"
        translator_format = "    * {1} <{0}> ({2})"
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
                    ((t[0], t[1], t[2]) for t in translators),
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


COUNT_DEFAULTS = {
    field: 0
    for field in (
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
    )
}


def generate_counts(user, start_date, end_date, **kwargs):
    """Generate credits data for given component."""
    result = {}
    action_map = {Change.ACTION_NEW: "new", Change.ACTION_APPROVE: "approve"}

    base = Change.objects.content().filter(unit__isnull=False)
    if user:
        base = base.filter(author=user)
    else:
        base = base.filter(author__isnull=False)

    changes = base.filter(
        timestamp__range=(start_date, end_date), **kwargs
    ).prefetch_related("author", "unit")
    for change in changes:
        email = change.author.email

        if email not in result:
            result[email] = current = {"name": change.author.full_name, "email": email}
            current.update(COUNT_DEFAULTS)
        else:
            current = result[email]

        src_chars = len(change.unit.source)
        src_words = change.unit.num_words
        tgt_chars = len(change.target)
        tgt_words = len(change.target.split())
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

    return list(result.values())


@login_required
@require_POST
def get_counts(request, project=None, component=None):
    """View for work counts."""
    if project is None:
        obj = None
        kwargs = {}
    elif component is None:
        obj = get_project(request, project)
        kwargs = {"project": obj}
    else:
        obj = get_component(request, project, component)
        kwargs = {"component": obj}

    form = ReportsForm(request.POST)

    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj or "home", "#reports")

    data = generate_counts(
        None if request.user.has_perm("reports.view", obj) else request.user,
        form.cleaned_data["start_date"],
        form.cleaned_data["end_date"],
        **kwargs,
    )

    if form.cleaned_data["style"] == "json":
        return JsonResponse(data=data, safe=False)

    headers = (
        "Name",
        "Email",
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
            " ".join(f"{h:40}" for h in headers[:2]),
            " ".join(f"{h:24}" for h in headers[2:]),
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
