#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
from django.views.decorators.http import require_POST

from weblate.lang.models import Language
from weblate.trans.forms import ReportsForm
from weblate.trans.models.change import Change
from weblate.trans.util import redirect_param
from weblate.utils.views import get_component, get_project, show_form_errors

# Header, two longer fields for name and email, shorter fields for numbers
RST_HEADING = " ".join(["=" * 40] * 2 + ["=" * 24] * 20)

HTML_HEADING = "<table>\n<tr>{0}</tr>"


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
        start = "<table>"
        row_start = "<tr>"
        language_format = "<th>{0}</th>"
        translator_start = "<td><ul>"
        translator_format = '<li><a href="mailto:{0}">{1}</a> ({2})</li>'
        translator_end = "</ul></td>"
        row_end = "</tr>"
        mime = "text/html"
        end = "</table>"
    else:
        start = ""
        row_start = ""
        language_format = "* {0}\n"
        translator_start = ""
        translator_format = "    * {1} <{0}> ({2})"
        translator_end = ""
        row_end = ""
        mime = "text/plain"
        end = ""

    result = []

    result.append(start)

    for language in data:
        name, translators = language.popitem()
        result.append(row_start)
        result.append(language_format.format(name))
        result.append(
            translator_start
            + "\n".join(translator_format.format(*t) for t in translators)
            + translator_end
        )
        result.append(row_end)

    result.append(end)

    return HttpResponse("\n".join(result), content_type=f"{mime}; charset=utf-8")


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
        start = HTML_HEADING.format("".join(f"<th>{h}</th>" for h in headers))
        row_start = "<tr>"
        cell_name = cell_count = "<td>{0}</td>\n"
        row_end = "</tr>"
        mime = "text/html"
        end = "</table>"
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

    result = []

    result.append(start)

    for item in data:
        if row_start:
            result.append(row_start)
        result.append(
            "".join(
                (
                    cell_name.format(item["name"] or "Anonymous"),
                    cell_name.format(item["email"] or ""),
                    cell_count.format(item["count"]),
                    cell_count.format(item["edits"]),
                    cell_count.format(item["words"]),
                    cell_count.format(item["chars"]),
                    cell_count.format(item["t_words"]),
                    cell_count.format(item["t_chars"]),
                    cell_count.format(item["count_new"]),
                    cell_count.format(item["edits_new"]),
                    cell_count.format(item["words_new"]),
                    cell_count.format(item["chars_new"]),
                    cell_count.format(item["t_words_new"]),
                    cell_count.format(item["t_chars_new"]),
                    cell_count.format(item["count_approve"]),
                    cell_count.format(item["edits_approve"]),
                    cell_count.format(item["words_approve"]),
                    cell_count.format(item["chars_approve"]),
                    cell_count.format(item["t_words_approve"]),
                    cell_count.format(item["t_chars_approve"]),
                    cell_count.format(item["count_edit"]),
                    cell_count.format(item["edits_edit"]),
                    cell_count.format(item["words_edit"]),
                    cell_count.format(item["chars_edit"]),
                    cell_count.format(item["t_words_edit"]),
                    cell_count.format(item["t_chars_edit"]),
                )
            )
        )
        if row_end:
            result.append(row_end)

    result.append(end)

    return HttpResponse("\n".join(result), content_type=f"{mime}; charset=utf-8")
