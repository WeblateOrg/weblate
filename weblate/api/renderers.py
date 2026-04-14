# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass

from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework_csv.renderers import CSVRenderer


@dataclass(frozen=True)
class OpenMetricsSample:
    value: int | float
    labels: dict[str, str]


def format_openmetrics_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


class OpenMetricsRenderer(BaseRenderer):
    media_type = "application/openmetrics-text"
    format = "openmetrics"
    charset = "utf-8"
    render_style = "text"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        result = []
        for key, value in data.items():
            if isinstance(value, str):
                # Strings not supported
                continue
            if isinstance(value, (int, float)):
                result.append(f"{key} {value}")
            elif isinstance(value, OpenMetricsSample):
                labels = ",".join(
                    f'{label}="{format_openmetrics_label(label_value)}"'
                    for label, label_value in value.labels.items()
                )
                result.append(
                    f"{key}{{{labels}}} {value.value}"
                    if labels
                    else f"{key} {value.value}"
                )
            elif isinstance(value, dict):
                # Celery queues
                for queue, stat in value.items():
                    result.append(f'{key}{{queue="{queue}"}} {stat}')

        result.append("# EOF")
        return "\n".join(result)


class FlatBaseRenderer(BaseRenderer):
    results_field = "results"

    def render(self, data, *args, **kwargs):
        if isinstance(data, dict) and self.results_field in data:
            data = data[self.results_field]
        return super().render(data, *args, **kwargs)


class AutoCSVRenderer(FlatBaseRenderer, CSVRenderer):
    """Automatically expand paginated results."""


class FlatJsonRenderer(FlatBaseRenderer, JSONRenderer):
    format = "json-flat"
