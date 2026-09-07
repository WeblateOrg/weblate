# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework_csv.renderers import CSVRenderer

if TYPE_CHECKING:
    from collections.abc import Mapping

OpenMetricsMetricType = Literal[
    "counter",
    "gauge",
    "histogram",
    "gaugehistogram",
    "summary",
    "info",
    "stateset",
    "unknown",
]


@dataclass(frozen=True)
class OpenMetricsSample:
    value: int | float
    labels: Mapping[str, str]


@dataclass(frozen=True)
class OpenMetricsMetric:
    name: str
    help_text: str
    metric_type: OpenMetricsMetricType
    samples: tuple[OpenMetricsSample, ...]


def format_openmetrics_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def format_openmetrics_help(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n")


class OpenMetricsRenderer(BaseRenderer):
    media_type = "application/openmetrics-text"
    response_content_type = "application/openmetrics-text; version=1.0.0; charset=utf-8"
    format = "openmetrics"
    charset = "utf-8"
    render_style = "text"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        result: list[str] = []
        for metric in data:
            if not isinstance(metric, OpenMetricsMetric):
                continue
            result.extend(
                (
                    f"# HELP {metric.name} {format_openmetrics_help(metric.help_text)}",
                    f"# TYPE {metric.name} {metric.metric_type}",
                )
            )
            for sample in metric.samples:
                labels = ",".join(
                    f'{label}="{format_openmetrics_label(label_value)}"'
                    for label, label_value in sample.labels.items()
                )
                result.append(
                    f"{metric.name}{{{labels}}} {sample.value}"
                    if labels
                    else f"{metric.name} {sample.value}"
                )

        result.append("# EOF")
        return "\n".join(result) + "\n"


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
