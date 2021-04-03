#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Charting library for Weblate."""

from typing import Optional

from django.http import JsonResponse

from weblate.metrics.models import Metric
from weblate.metrics.wrapper import MetricsWrapper


def monthly_activity_json(
    request,
    project: Optional[str] = None,
    component: Optional[str] = None,
    lang: Optional[str] = None,
    user: Optional[str] = None,
):
    """Return monthly activity for matching changes as json."""
    metrics = MetricsWrapper(None, Metric.SCOPE_GLOBAL, 0)
    return JsonResponse(data=metrics.daily_activity, safe=False)
