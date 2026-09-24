# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Charting library for Weblate."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.http import JsonResponse

from weblate.metrics.models import Metric
from weblate.metrics.wrapper import MetricsWrapper

if TYPE_CHECKING:
    from django.http import HttpRequest


def monthly_activity_json(
    request: HttpRequest,
    project: str | None = None,
    component: str | None = None,
    lang: str | None = None,
    user: str | None = None,
) -> JsonResponse:
    """Return monthly activity for matching changes as json."""
    metrics = MetricsWrapper(None, Metric.SCOPE_GLOBAL, 0)
    return JsonResponse(data=metrics.daily_activity, safe=False)
