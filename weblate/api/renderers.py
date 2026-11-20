# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rest_framework import serializers
from rest_framework.renderers import (
    BaseRenderer,
    BrowsableAPIRenderer,
    HTMLFormRenderer,
    JSONRenderer,
)
from rest_framework_csv.renderers import CSVRenderer

from weblate.utils.csv import escape_csv_formula

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from rest_framework.utils.serializer_helpers import BoundField


class WeblateHTMLFormRenderer(HTMLFormRenderer):
    choice_select_limit = 100

    def render_field(self, field: BoundField, parent_style: Mapping[str, Any]) -> str:
        serializer_field = field._field  # ruff: ignore[private-member-access]
        if isinstance(serializer_field, serializers.RelatedField) or (
            isinstance(serializer_field, serializers.ChoiceField)
            and not isinstance(serializer_field, serializers.MultipleChoiceField)
            and len(serializer_field.choices) > self.choice_select_limit
        ):
            # Override the bound field's presentation for this render only.
            field.style = {  # type: ignore[attr-defined]
                **field.style,
                "base_template": "input.html",
                "input_type": "text",
            }
        return super().render_field(field, parent_style)


class WeblateBrowsableAPIRenderer(BrowsableAPIRenderer):
    form_renderer_class = WeblateHTMLFormRenderer


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

    def tablize(self, data, header=None, labels=None):
        for row in super().tablize(data, header=header, labels=labels):
            yield [
                escape_csv_formula(value) if isinstance(value, str) else value
                for value in row
            ]


class FlatJsonRenderer(FlatBaseRenderer, JSONRenderer):
    format = "json-flat"
