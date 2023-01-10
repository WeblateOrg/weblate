# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig


class MetricsConfig(AppConfig):
    name = "weblate.metrics"
    label = "metrics"
    verbose_name = "Metrics"
