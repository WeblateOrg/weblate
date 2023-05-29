# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import csv

from django.http import HttpResponse, JsonResponse

from weblate.api.serializers import StatisticsSerializer
from weblate.trans.stats import get_project_stats
from weblate.utils.views import get_component, get_project


def export_stats_project(request, project):
    """Export stats in JSON format."""
    obj = get_project(request, project)

    return export_response(
        request,
        f"stats-{obj.slug}.csv",
        (
            "language",
            "code",
            "total",
            "translated",
            "translated_percent",
            "total_words",
            "translated_words",
            "translated_words_percent",
            "total_chars",
            "translated_chars",
            "translated_chars_percent",
        ),
        get_project_stats(obj),
    )


def export_stats(request, project, component):
    """Export stats in JSON format."""
    subprj = get_component(request, project, component)
    translations = subprj.translation_set.order_by("language_code")

    return export_response(
        request,
        f"stats-{subprj.project.slug}-{subprj.slug}.csv",
        (
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
        ),
        StatisticsSerializer(translations, many=True).data,
    )


def export_response(request, filename, fields, data):
    """Generic handler for stats exports."""
    output = request.GET.get("format", "json")
    if output not in ("json", "csv"):
        output = "json"

    if output == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f"attachment; filename={filename}"

        writer = csv.DictWriter(response, fields)

        writer.writeheader()
        for row in data:
            writer.writerow(row)
        return response
    return JsonResponse(data=data, safe=False, json_dumps_params={"indent": 2})
