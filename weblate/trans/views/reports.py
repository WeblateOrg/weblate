# Copyright © Michal Čihař <michal@weblate.org>
# Copyright © WofWca <wofwca@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from weblate.lang.models import Language
from weblate.memory.machine import WeblateMemory
from weblate.trans.actions import ActionEvents
from weblate.trans.autotranslate import fetch_machinery_matches
from weblate.trans.forms import (
    CostEstimateReportsForm,
    CountsReportsForm,
    ReportsForm,
    TranslatorWorkReportsForm,
)
from weblate.trans.models import (
    Category,
    Change,
    Component,
    Project,
    Report,
    Translation,
    Unit,
)
from weblate.trans.translator_analysis import analyze_translator_work
from weblate.trans.util import count_words, redirect_param
from weblate.utils.celery import store_task_metadata
from weblate.utils.state import FUZZY_STATES, STATE_READONLY
from weblate.utils.views import parse_path, show_form_errors
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from django.db.models import Model
    from django.utils.safestring import SafeString

    from weblate.auth.models import AuthenticatedHttpRequest, User

# Header, three longer fields for name, email and date joined, shorter fields for numbers
RST_HEADING = " ".join(["=" * 40] * 3 + ["=" * 24] * 24)

HTML_HEADING = "<table>\n<tr>{0}</tr>"
COST_RST_HEADING = " ".join(["=" * 24] * 6)
COST_BUCKETS = (
    ("repetition", "rate_repetition"),
    ("tm_100", "rate_tm_100"),
    ("tm_fuzzy", "rate_tm_fuzzy"),
    ("needs_editing", "rate_needs_editing"),
    ("new", "rate_new"),
)
COST_ESTIMATE_MATCH_BATCH_SIZE = 200

REPORT_SCOPE_MODELS = {
    "workspace": Workspace,
    "project": Project,
    "category": Category,
    "component": Component,
}


def get_report_scope(request: AuthenticatedHttpRequest, path=None):
    return parse_path(request, path, (Component, Category, Project, Workspace, None))


def get_report_scope_values(scope) -> tuple[str, str]:
    if scope is None:
        return "", ""
    for scope_type, model in REPORT_SCOPE_MODELS.items():
        if isinstance(scope, model):
            return scope_type, str(scope.pk)
    msg = f"Unsupported report scope: {scope!r}"
    raise TypeError(msg)


def get_report_form_scope(scope) -> dict[str, Model]:
    scope_type, _scope_id = get_report_scope_values(scope)
    return {scope_type: scope} if scope_type else {}


def get_reports_context(request: AuthenticatedHttpRequest, scope) -> dict[str, Any]:
    form_scope = get_report_form_scope(scope)
    scope_type, _scope_id = get_report_scope_values(scope)
    scope_filter = (
        {scope_type: scope}
        if scope_type
        else {
            "workspace__isnull": True,
            "project__isnull": True,
            "category__isnull": True,
            "component__isnull": True,
        }
    )
    reports = (
        Report.objects.select_related(
            "creator", "workspace", "project", "category", "component"
        )
        .metadata()
        .filter(**scope_filter)
        .filter_access(request.user)
    )
    paginator = Paginator(reports, 20)
    try:
        report_page = paginator.page(request.GET.get("reports_page", 1))
    except EmptyPage:
        report_page = paginator.page(paginator.num_pages)
    except PageNotAnInteger:
        report_page = paginator.page(1)
    return {
        "object": scope,
        "reports_form": ReportsForm(form_scope),
        "reports_count_form": CountsReportsForm(form_scope),
        "reports_cost_form": CostEstimateReportsForm(form_scope),
        "reports_translator_work_form": TranslatorWorkReportsForm(form_scope),
        "generated_reports": report_page,
    }


def load_report_scope(scope_type: str, scope_id: str):
    if not scope_type:
        return None
    try:
        model = REPORT_SCOPE_MODELS[scope_type]
    except KeyError as error:
        msg = f"Unsupported report scope: {scope_type}"
        raise ValueError(msg) from error
    return model.objects.get(pk=scope_id)


def parse_report_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def collect_report_data(
    kind: str,
    parameters: dict[str, Any],
    creator: User,
    scope: Workspace | Project | Category | Component | None,
):
    report_user = creator if parameters.get("own_data") else None
    if kind == Report.Kind.CREDITS:
        return generate_credits(
            report_user,
            parse_report_datetime(parameters["start"]),
            parse_report_datetime(parameters["end"]),
            parameters.get("language", ""),
            scope,
            parameters.get("sort_by", "count"),
            parameters.get("sort_order", "descending"),
        )
    if kind == Report.Kind.CONTRIBUTOR_STATS:
        scope_type, _scope_id = get_report_scope_values(scope)
        scope_values = {scope_type: scope} if scope_type else {}
        return generate_counts(
            report_user,
            parse_report_datetime(parameters["start"]),
            parse_report_datetime(parameters["end"]),
            parameters.get("language", ""),
            parameters.get("sort_by", "count"),
            parameters.get("sort_order", "descending"),
            parameters.get("counting_mode", CountsReportsForm.COUNTING_MODE_UNIQUE),
            **scope_values,
        )
    if kind == Report.Kind.COST_ESTIMATE:
        return generate_cost_estimate(
            creator,
            parameters.get("language", ""),
            parameters["q"],
            Decimal(parameters["base_rate"]),
            parameters["tm_threshold"],
            {
                key: Decimal(parameters[key])
                for key in (
                    "rate_new",
                    "rate_needs_editing",
                    "rate_tm_100",
                    "rate_tm_fuzzy",
                    "rate_repetition",
                )
            },
            scope,
        )
    if kind == Report.Kind.TRANSLATOR_WORK:
        return analyze_translator_work(
            since=parse_report_datetime(parameters["start"]),
            until=parse_report_datetime(parameters["end"]),
            scope=scope,
            language=parameters.get("language", ""),
            user=report_user,
            access_user=creator,
            min_changes=parameters["min_changes"],
            max_changes=parameters["max_changes"],
            max_words=parameters["max_words"],
        )
    msg = f"Unsupported report kind: {kind}"
    raise ValueError(msg)


def schedule_web_report(
    request: AuthenticatedHttpRequest,
    scope,
    kind: str,
    parameters: dict[str, Any],
):
    # ruff: ignore[import-outside-top-level]
    from weblate.trans.tasks import generate_report

    scope_type, scope_id = get_report_scope_values(scope)
    task_kwargs = {
        "kind": kind,
        "parameters": parameters,
        "user_id": request.user.pk,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "target": "web",
    }
    if settings.CELERY_TASK_ALWAYS_EAGER:
        result = generate_report(**task_kwargs)
        return redirect_param(result["url"], "")
    task = generate_report.delay(**task_kwargs)
    store_task_metadata(task.id, user_id=request.user.id)
    messages.success(request, gettext("Generating report…"), f"task:{task.id}")
    return redirect_param(scope or "home", "#reports")


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


def format_decimal(value: Decimal, places: int = 4) -> str:
    result = f"{value:.{places}f}".rstrip("0").rstrip(".")
    return result or "0"


def get_cost_bucket_name(bucket: str) -> str:
    names = {
        "repetition": gettext("Repetitions"),
        "tm_100": gettext("Exact matches"),
        "tm_fuzzy": gettext("Fuzzy matches"),
        "needs_editing": gettext("Needs editing"),
        "new": gettext("New strings"),
    }
    return names[bucket]


def get_cost_estimate_units(
    user: User,
    language_code: str,
    entity: Workspace | Project | Component | Category | None,
):
    translations = Translation.objects.exclude_source().filter_access(user)
    if language_code:
        translations = translations.filter(language__code=language_code)

    if isinstance(entity, Workspace):
        translations = translations.filter(component__project__workspace=entity)
    elif isinstance(entity, Project):
        translations = translations.filter(component__project=entity)
    elif isinstance(entity, Category):
        translations = translations.filter(component_id__in=entity.all_component_ids)
    elif isinstance(entity, Component):
        translations = translations.filter(component=entity)
    return Unit.objects.filter(translation__in=translations).exclude(
        state=STATE_READONLY
    )


def get_match_quality(unit: Unit) -> int:
    return min(unit.machinery.get("quality", (0,)), default=0)


def add_unit_to_bucket(bucket: dict[str, Any], unit: Unit) -> None:
    bucket["count"] += 1
    bucket["words"] += unit.num_words
    bucket["chars"] += len(unit.source)


def process_cost_estimate_matches(
    *,
    units: list[Unit],
    user: User,
    service: WeblateMemory,
    tm_threshold: int,
    buckets: dict[str, dict[str, Any]],
) -> None:
    fetch_machinery_matches(
        units=units,
        user=user,
        services=[service],
        threshold=100,
    )
    fuzzy_units = [unit for unit in units if get_match_quality(unit) < 100]
    if tm_threshold < 100:
        fetch_machinery_matches(
            units=fuzzy_units,
            user=user,
            services=[service],
            threshold=tm_threshold,
        )

    for unit in units:
        quality = get_match_quality(unit)
        if quality >= 100:
            bucket = "tm_100"
        elif quality >= tm_threshold:
            bucket = "tm_fuzzy"
        elif unit.state in FUZZY_STATES:
            bucket = "needs_editing"
        else:
            bucket = "new"
        add_unit_to_bucket(buckets[bucket], unit)


def finalize_cost_estimate(data: dict[str, Any], base_rate: Decimal) -> dict[str, Any]:
    total = {"count": 0, "words": 0, "chars": 0, "cost": Decimal(0)}

    for bucket in data["buckets"]:
        bucket["cost"] = Decimal(bucket["words"]) * base_rate * bucket["rate"] / 100
        total["count"] += bucket["count"]
        total["words"] += bucket["words"]
        total["chars"] += bucket["chars"]
        total["cost"] += bucket["cost"]
        bucket["rate"] = format_decimal(bucket["rate"], 2)
        bucket["cost"] = format_decimal(bucket["cost"])

    total["cost"] = format_decimal(total["cost"])
    data["total"] = total
    data["base_rate"] = format_decimal(base_rate)
    return data


def generate_cost_estimate(
    user: User,
    language_code: str,
    q: str,
    base_rate: Decimal,
    tm_threshold: int,
    rates: dict[str, Decimal],
    entity: Workspace | Project | Component | Category | None,
) -> dict[str, Any]:
    buckets = {
        bucket: {
            "slug": bucket,
            "name": get_cost_bucket_name(bucket),
            "count": 0,
            "words": 0,
            "chars": 0,
            "rate": rates[rate_field],
            "cost": Decimal(0),
        }
        for bucket, rate_field in COST_BUCKETS
    }
    data: dict[str, Any] = {
        "threshold": tm_threshold,
        "buckets": [buckets[bucket] for bucket, _rate_field in COST_BUCKETS],
    }
    seen_sources: set[tuple[int, int, int]] = set()
    match_batches: dict[tuple[int, int, int], list[Unit]] = defaultdict(list)
    service = WeblateMemory({})

    for unit in (
        get_cost_estimate_units(user, language_code, entity)
        .search(q, parser="unit")
        .prefetch()
        .order()
        .iterator(chunk_size=1000)
    ):
        translation = unit.translation
        component = translation.component
        key = (
            component.source_language_id,
            translation.language_id,
            unit.id_hash,
        )
        if key in seen_sources:
            add_unit_to_bucket(buckets["repetition"], unit)
            continue

        seen_sources.add(key)
        match_key = (
            component.source_language_id,
            translation.language_id,
            translation.plural_id,
        )
        match_batches[match_key].append(unit)
        if len(match_batches[match_key]) >= COST_ESTIMATE_MATCH_BATCH_SIZE:
            process_cost_estimate_matches(
                units=match_batches.pop(match_key),
                user=user,
                service=service,
                tm_threshold=tm_threshold,
                buckets=buckets,
            )

    for units in match_batches.values():
        process_cost_estimate_matches(
            units=units,
            user=user,
            service=service,
            tm_threshold=tm_threshold,
            buckets=buckets,
        )

    return finalize_cost_estimate(data, base_rate)


def render_cost_estimate(data: dict[str, Any], style: str) -> HttpResponse:
    headers = (
        gettext("Category"),
        gettext("Strings"),
        gettext("Source words"),
        gettext("Source characters"),
        gettext("Rate"),
        gettext("Cost"),
    )

    if style == "html":
        start = format_html(
            HTML_HEADING,
            format_html_join("", "<th>{}</th>", ((header,) for header in headers)),
        )
        row_start = "<tr>"
        cell = "<td>{0}</td>\n"
        row_end = "</tr>"
        mime = "text/html"
        end = "</table>"
        format_html_or_plain = format_html
        format_html_or_plain_join = format_html_join
    else:
        start = (
            f"{COST_RST_HEADING}\n"
            f"{headers[0]:24} {headers[1]:24} {headers[2]:24} "
            f"{headers[3]:24} {headers[4]:24} {headers[5]:24}\n"
            f"{COST_RST_HEADING}"
        )
        row_start = ""
        cell = "{0:24} "
        row_end = ""
        mime = "text/plain"
        end = COST_RST_HEADING
        format_html_or_plain = format_plaintext
        format_html_or_plain_join = format_plaintext_join

    result = [start]

    for item in data["buckets"]:
        if row_start:
            result.append(row_start)
        result.append(
            format_html_or_plain_join(
                "",
                "{}",
                (
                    (format_html_or_plain(cell, item["name"]),),
                    (format_html_or_plain(cell, item["count"]),),
                    (format_html_or_plain(cell, item["words"]),),
                    (format_html_or_plain(cell, item["chars"]),),
                    (format_html_or_plain(cell, f"{item['rate']}%"),),
                    (format_html_or_plain(cell, item["cost"]),),
                ),
            )
        )
        if row_end:
            result.append(row_end)

    if row_start:
        result.append(row_start)
    result.append(
        format_html_or_plain_join(
            "",
            "{}",
            (
                (format_html_or_plain(cell, gettext("Total")),),
                (format_html_or_plain(cell, data["total"]["count"]),),
                (format_html_or_plain(cell, data["total"]["words"]),),
                (format_html_or_plain(cell, data["total"]["chars"]),),
                (format_html_or_plain(cell, ""),),
                (format_html_or_plain(cell, data["total"]["cost"]),),
            ),
        )
    )
    if row_end:
        result.append(row_end)

    result.append(end)

    return HttpResponse("\n".join(result), content_type=f"{mime}; charset=utf-8")


@login_required
@require_POST
def get_costs(request: AuthenticatedHttpRequest, path=None):
    """View for cost estimates."""
    obj = get_report_scope(request, path)
    scope = get_report_form_scope(obj)

    if not request.user.has_perm("reports.view", obj):
        raise PermissionDenied

    form = CostEstimateReportsForm(scope, request.POST)

    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj or "home", "#reports")

    parameters = {
        "language": form.cleaned_data["language"],
        "q": form.cleaned_data["q"],
        "base_rate": str(form.cleaned_data["base_rate"]),
        "tm_threshold": form.cleaned_data["tm_threshold"],
        **{
            key: str(form.cleaned_data[key])
            for key in (
                "rate_new",
                "rate_needs_editing",
                "rate_tm_100",
                "rate_tm_fuzzy",
                "rate_repetition",
            )
        },
    }
    return schedule_web_report(request, obj, Report.Kind.COST_ESTIMATE, parameters)


def generate_credits(
    user: User | None,
    start_date,
    end_date,
    language_code: str,
    entity: Workspace | Project | Component | Category | None,
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
    elif isinstance(entity, Workspace):
        kwargs = {"translation__component__project__workspace": entity}
    elif isinstance(entity, Project):
        kwargs = {"translation__component__project": entity}
    elif isinstance(entity, Category):
        kwargs = {"translation__component_id__in": entity.all_component_ids}
    else:
        kwargs = {"translation__component": entity}

    languages = Language.objects.filter(**kwargs)
    if language_code:
        languages = languages.filter(code=language_code)

    order_by = "change_count" if sort_by == "count" else "author__date_joined"
    if sort_order == "descending":
        order_by = f"-{order_by}"

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
    obj = get_report_scope(request, path)
    scope = get_report_form_scope(obj)

    form = ReportsForm(scope, request.POST)

    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj or "home", "#reports")

    return schedule_web_report(
        request,
        obj,
        Report.Kind.CREDITS,
        {
            "start": form.cleaned_data["period"]["start_date"].isoformat(),
            "end": form.cleaned_data["period"]["end_date"].isoformat(),
            "language": form.cleaned_data["language"],
            "sort_by": form.cleaned_data["sort_by"],
            "sort_order": form.cleaned_data["sort_order"],
            "own_data": not request.user.has_perm("reports.view", obj),
        },
    )


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
    user: User | None,
    start_date,
    end_date,
    language_code: str,
    sort_by: str,
    sort_order: str,
    counting_mode: str = CountsReportsForm.COUNTING_MODE_UNIQUE,
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

    category = kwargs.pop("category", None)
    workspace = kwargs.pop("workspace", None)
    if workspace is not None:
        kwargs["project__workspace"] = workspace
    changes = base.filter(timestamp__range=(start_date, end_date), **kwargs)
    if category is not None:
        changes = changes.for_category(category)
    if counting_mode == CountsReportsForm.COUNTING_MODE_UNIQUE:
        changes = changes.order_by("-timestamp", "-pk")
    changes = changes.prefetch_related("author", "language", "unit")
    seen_changes = set()
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

        suffix = action_map.get(change.action, "edit")
        if counting_mode == CountsReportsForm.COUNTING_MODE_UNIQUE:
            deduplicated_key = (change.author_id, change.unit_id, suffix)
            if deduplicated_key in seen_changes:
                continue
            seen_changes.add(deduplicated_key)

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

        current[f"t_chars_{suffix}"] += tgt_chars
        current[f"t_words_{suffix}"] += tgt_words
        current[f"chars_{suffix}"] += src_chars
        current[f"words_{suffix}"] += src_words
        current[f"edits_{suffix}"] += edits
        current[f"count_{suffix}"] += 1

    result_list = list(result.values())
    sort_by_key = "count" if sort_by == "count" else "date_joined"
    reverse = sort_order == "descending"
    result_list.sort(key=itemgetter(sort_by_key), reverse=reverse)

    return result_list


@login_required
@require_POST
def get_counts(request: AuthenticatedHttpRequest, path=None):
    """View for work counts."""
    obj = get_report_scope(request, path)
    kwargs = get_report_form_scope(obj)

    form = CountsReportsForm(kwargs, request.POST)

    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(obj or "home", "#reports")

    return schedule_web_report(
        request,
        obj,
        Report.Kind.CONTRIBUTOR_STATS,
        {
            "start": form.cleaned_data["period"]["start_date"].isoformat(),
            "end": form.cleaned_data["period"]["end_date"].isoformat(),
            "language": form.cleaned_data["language"],
            "sort_by": form.cleaned_data["sort_by"],
            "sort_order": form.cleaned_data["sort_order"],
            "counting_mode": form.cleaned_data.get("counting_mode")
            or CountsReportsForm.COUNTING_MODE_UNIQUE,
            "own_data": not request.user.has_perm("reports.view", obj),
        },
    )


def render_counts(data: list[dict[str, Any]], style: str) -> HttpResponse:
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

    if style == "html":
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
        long_headers = " ".join(f"{h:40}" for h in headers[:3])
        short_headers = " ".join(f"{h:24}" for h in headers[3:])
        start = f"{RST_HEADING}\n{long_headers} {short_headers}\n{RST_HEADING}"
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


def render_credits(data: list[dict[str, Any]], style: str) -> HttpResponse:
    if style == "html":
        rows = []
        for language in data:
            name, translators = next(iter(language.items()))
            rows.append(
                format_html(
                    "<tr><th>{}</th><td><ul>{}</ul></td></tr>",
                    name,
                    format_html_join(
                        "",
                        '<li><a href="mailto:{}">{} ({})</a> - {}</li>',
                        (
                            (
                                translator["email"],
                                translator["full_name"],
                                translator["username"],
                                translator["change_count"],
                            )
                            for translator in translators
                        ),
                    ),
                )
            )
        body = format_html(
            "<table><tbody>{}</tbody></table>",
            format_html_join("", "{}", ((row,) for row in rows)),
        )
        return HttpResponse(body, content_type="text/html; charset=utf-8")

    result = []
    for language in data:
        name, translators = next(iter(language.items()))
        result.append(f"* {name}\n")
        result.extend(
            f"    * {item['full_name']} ({item['username']}) "
            f"<{item['email']}> - {item['change_count']}"
            for item in translators
        )
        result.append("")
    return HttpResponse("\n".join(result), content_type="text/plain; charset=utf-8")


def render_translator_work(data: dict[str, Any], style: str) -> HttpResponse:
    labels = {
        "strings": gettext("Translated strings per day"),
        "words": gettext("Source words per day"),
        "median": gettext("Median"),
        "average": gettext("Average"),
        "p75": gettext("75th percentile"),
        "p90": gettext("90th percentile"),
    }
    if style == "html":
        rows = []
        for metric, values in data["metrics"].items():
            rows.extend(
                format_html(
                    "<tr><th>{}</th><td>{}</td><td>{:.0f}</td></tr>",
                    labels[metric],
                    labels[name],
                    value,
                )
                for name, value in values.items()
            )
        body = format_html(
            "<p>{}: {} / {}: {}</p><table><tbody>{}</tbody></table>",
            gettext("Included user days"),
            data["user_days"]["included"],
            gettext("Excluded user days"),
            data["user_days"]["excluded"],
            format_html_join("", "{}", ((row,) for row in rows)),
        )
        return HttpResponse(body, content_type="text/html; charset=utf-8")

    result = [
        gettext("Translator work analysis"),
        f"{gettext('Included user days')}: {data['user_days']['included']}",
        f"{gettext('Excluded user days')}: {data['user_days']['excluded']}",
        "",
    ]
    for metric, values in data["metrics"].items():
        result.append(f"{labels[metric]}:")
        result.extend(
            f"  {labels[name]}: {value:.0f}" for name, value in values.items()
        )
    return HttpResponse("\n".join(result), content_type="text/plain; charset=utf-8")


def render_report_data(report: Report, style: str) -> HttpResponse:
    if style == "json":
        return JsonResponse(report.data, safe=not isinstance(report.data, list))
    if report.kind == Report.Kind.CREDITS:
        return render_credits(report.data, style)
    if report.kind == Report.Kind.CONTRIBUTOR_STATS:
        return render_counts(report.data, style)
    if report.kind == Report.Kind.COST_ESTIMATE:
        return render_cost_estimate(report.data, style)
    if report.kind == Report.Kind.TRANSLATOR_WORK:
        return render_translator_work(report.data, style)
    msg = f"Unsupported report kind: {report.kind}"
    raise ValueError(msg)


def get_accessible_report(request: AuthenticatedHttpRequest, pk: int) -> Report:
    report = get_object_or_404(
        Report.objects.select_related(
            "creator", "workspace", "project", "category", "component"
        ),
        pk=pk,
    )
    if not report.can_access(request.user):
        raise Http404
    return report


@login_required
@require_POST
def get_translator_work(request: AuthenticatedHttpRequest, path=None):
    scope = get_report_scope(request, path)
    if not request.user.has_perm("reports.view", scope):
        raise PermissionDenied
    form = TranslatorWorkReportsForm(get_report_form_scope(scope), request.POST)
    if not form.is_valid():
        show_form_errors(request, form)
        return redirect_param(scope or "home", "#reports")
    return schedule_web_report(
        request,
        scope,
        Report.Kind.TRANSLATOR_WORK,
        {
            "start": form.cleaned_data["period"]["start_date"].isoformat(),
            "end": form.cleaned_data["period"]["end_date"].isoformat(),
            "language": form.cleaned_data["language"],
            "min_changes": form.cleaned_data["min_changes"],
            "max_changes": form.cleaned_data["max_changes"],
            "max_words": form.cleaned_data["max_words"],
            "own_data": False,
        },
    )


@login_required
def report_detail(request: AuthenticatedHttpRequest, pk: int) -> HttpResponse:
    report_obj = get_accessible_report(request, pk)
    rendered = render_report_data(report_obj, "html")
    return render(
        request,
        "report.html",
        {
            "object": report_obj.scope,
            "report": report_obj,
            # The HTML renderer escapes every value through format_html.
            "report_html": mark_safe(rendered.content.decode()),  # ruff: ignore[suspicious-mark-safe-usage]
        },
    )
