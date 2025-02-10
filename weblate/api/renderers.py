# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework_csv.renderers import CSVRenderer


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
            if isinstance(value, int | float):
                result.append(f"{key} {value}")
            elif isinstance(value, dict):
                # Celery queues
                for queue, stat in value.items():
                    result.append(f'{key}(queue="{queue}") {stat}')

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
