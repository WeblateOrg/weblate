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

from datetime import datetime
from typing import Callable, Optional

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import pgettext

from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.trans.models import Change
from weblate.utils.views import get_percent_color, get_project_translation


def cache_key(*args):
    def makekey(val):
        if not val:
            return "0"
        if hasattr(val, "id"):
            return str(val.id)
        return str(val)

    return "activity-{}".format("-".join(makekey(arg) for arg in args))


def get_activity_stats(
    request,
    days: int,
    step: int,
    project: Optional[str] = None,
    component: Optional[str] = None,
    lang: Optional[str] = None,
    user: Optional[str] = None,
):
    """Parse json stats URL params."""
    if project is None and lang is None and user is None:
        project = None
        component = None
        translation = None
        language = None
        user = None
    elif user is not None:
        project = None
        component = None
        translation = None
        language = None
        user = get_object_or_404(User, username=user)
    elif project is None:
        project = None
        component = None
        translation = None
        language = get_object_or_404(Language, code=lang)
        user = None
    else:
        # Process parameters
        project, component, translation = get_project_translation(
            request, project, component, lang
        )
        language = None
        user = None

    key = cache_key(days, step, project, component, translation, language, user)
    result = cache.get(key)
    if not result:
        # Get actual stats
        result = Change.objects.base_stats(
            days, step, project, component, translation, language, user
        )
        cache.set(key, result, 3600 * 4)
    return result


def get_label_month(pos: int, previous_month: int, timestamp: datetime) -> str:
    if previous_month != timestamp.month:
        return pgettext(
            "Format string for yearly activity chart", "{month}/{year}"
        ).format(month=timestamp.month, year=timestamp.year)
    return ""


def get_label_day(pos: int, previous_month: int, timestamp: datetime) -> str:
    if pos % 5 == 0:
        return pgettext(
            "Format string for monthly activity chart", "{day}/{month}"
        ).format(day=timestamp.day, month=timestamp.month, year=timestamp.year)
    return ""


def render_activity(
    request,
    days: int,
    step: int,
    label_func: Callable[[int, int, datetime], str],
    project: Optional[str] = None,
    component: Optional[str] = None,
    lang: Optional[str] = None,
    user: Optional[str] = None,
):
    """Return activity for matching changes and interval as SVG chart."""
    activity = get_activity_stats(request, days, step, project, component, lang, user)

    max_value = max(item[1] for item in activity)

    serie = []
    previous_month = -1
    offset = 0
    for pos, item in enumerate(activity):
        timestamp, value = item
        percent = value * 100 // max_value if max_value else 0
        if value and percent < 4:
            percent = 4
        label = label_func(pos, previous_month, timestamp)
        previous_month = timestamp.month
        offset += 15
        height = int(1.5 * percent)
        serie.append(
            (
                value,
                label,
                offset,
                get_percent_color(percent),
                height,
                10 + (150 - height),
            )
        )

    return render(
        request, "svg/activity.svg", {"serie": serie}, content_type="image/svg+xml"
    )


def yearly_activity(
    request,
    project: Optional[str] = None,
    component: Optional[str] = None,
    lang: Optional[str] = None,
    user: Optional[str] = None,
):
    """Return yearly activity for matching changes as SVG chart."""
    return render_activity(
        request, 364, 7, get_label_month, project, component, lang, user
    )


def monthly_activity(
    request,
    project: Optional[str] = None,
    component: Optional[str] = None,
    lang: Optional[str] = None,
    user: Optional[str] = None,
):
    """Return monthly activity for matching changes as SVG chart."""
    return render_activity(
        request, 52, 1, get_label_day, project, component, lang, user
    )


def monthly_activity_json(
    request,
    project: Optional[str] = None,
    component: Optional[str] = None,
    lang: Optional[str] = None,
    user: Optional[str] = None,
):
    """Return monthly activity for matching changes as json."""
    activity = get_activity_stats(request, 52, 1, project, component, lang, user)

    return JsonResponse(data=[item[1] for item in activity], safe=False)
