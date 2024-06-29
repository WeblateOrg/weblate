# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from rest_framework.renderers import BaseRenderer


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
