# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import csv
from typing import TYPE_CHECKING

from django.http import HttpResponse, JsonResponse

from weblate.api.serializers import StatisticsSerializer
from weblate.trans.models import Component, Project
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


def export_stats(request: AuthenticatedHttpRequest, path):
    """Export stats in JSON or CSV format."""
    obj = parse_path(request, path, (Project, Component))
    if isinstance(obj, Project):
        return export_response(
            request, f"stats-{obj.slug}.csv", obj.stats.get_language_stats()
        )

    translations = obj.translation_set.order_by("language_code")
    return export_response(
        request, f"stats-{obj.project.slug}-{obj.slug}.csv", translations
    )


def export_response(request: AuthenticatedHttpRequest, filename, objects):
    """Generate stats response."""
    fields = (
        "name",
        "code",
        "total",
        "translated",
        "translated_percent",
        "translated_words_percent",
        "total_words",
        "translated_words",
        "total_chars",
        "translated_chars",
        "translated_chars_percent",
        "failing",
        "failing_percent",
        "fuzzy",
        "fuzzy_percent",
        "url_translate",
        "url",
        "translate_url",
        "last_change",
        "last_author",
        "recent_changes",
        "readonly",
        "readonly_percent",
        "approved",
        "approved_percent",
        "suggestions",
        "comments",
    )
    data = StatisticsSerializer(objects, many=True).data
    output = request.GET.get("format", "json")
    if output not in {"json", "csv"}:
        output = "json"

    if output == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f"attachment; filename={filename}"

        writer = csv.DictWriter(response, fields, extrasaction="ignore")

        writer.writeheader()
        for row in data:
            writer.writerow(row)
        return response
    return JsonResponse(data=data, safe=False, json_dumps_params={"indent": 2})
