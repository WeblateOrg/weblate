# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from django.conf import settings
from rest_framework.renderers import JSONRenderer

from weblate.api.renderers import (
    AutoCSVRenderer,
    OpenMetricsMetric,
    OpenMetricsRenderer,
    OpenMetricsSample,
)
from weblate.api.serializers import MetricsSerializer
from weblate.utils.stats import GlobalStats
from weblate.utils.version import GIT_VERSION
from weblate.utils.version_display import show_metrics_version

if TYPE_CHECKING:
    from collections.abc import Mapping

MetricsFormat = Literal["json", "csv", "openmetrics"]
METRICS_FORMATS: tuple[MetricsFormat, ...] = ("json", "csv", "openmetrics")

OPENMETRICS_METRIC_HELP = (
    ("units", "Number of translation units."),
    ("units_translated", "Number of translated translation units."),
    ("users", "Number of users."),
    ("changes", "Number of recorded changes."),
    ("projects", "Number of projects."),
    ("components", "Number of components."),
    ("translations", "Number of translations."),
    ("languages", "Number of configured languages."),
    ("checks", "Number of triggered quality checks."),
    ("configuration_errors", "Number of active configuration errors."),
    ("suggestions", "Number of pending suggestions."),
)


def get_server_metrics_data() -> dict[str, object]:
    return dict(MetricsSerializer(GlobalStats()).data)


def get_server_openmetrics_data(
    data: Mapping[str, object],
) -> list[OpenMetricsMetric]:
    result = [
        OpenMetricsMetric(
            name=name,
            help_text=help_text,
            metric_type="gauge",
            samples=(OpenMetricsSample(value=cast("int", data[name]), labels={}),),
        )
        for name, help_text in OPENMETRICS_METRIC_HELP
    ]
    queues = cast("Mapping[str, int]", data["celery_queues"])
    result.append(
        OpenMetricsMetric(
            name="celery_queues",
            help_text="Number of tasks in each Celery queue.",
            metric_type="gauge",
            samples=tuple(
                OpenMetricsSample(value=value, labels={"queue": queue})
                for queue, value in queues.items()
            ),
        )
    )
    if show_metrics_version(settings.VERSION_DISPLAY):
        result.append(
            OpenMetricsMetric(
                name="weblate_info",
                help_text="Weblate build information.",
                metric_type="gauge",
                samples=(
                    OpenMetricsSample(
                        value=1,
                        labels={"version": GIT_VERSION},
                    ),
                ),
            )
        )
    return result


def render_server_metrics(output_format: MetricsFormat) -> str:
    data = get_server_metrics_data()
    if output_format == "openmetrics":
        rendered = OpenMetricsRenderer().render(get_server_openmetrics_data(data))
    elif output_format == "csv":
        rendered = AutoCSVRenderer().render(data)
    else:
        rendered = JSONRenderer().render(data)
    return rendered if isinstance(rendered, str) else rendered.decode()
