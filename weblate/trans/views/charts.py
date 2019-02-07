# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.utils.translation import pgettext

from weblate.auth.models import User
from weblate.trans.models import Change
from weblate.lang.models import Language
from weblate.utils.views import get_project_translation


def cache_key(*args):
    def makekey(val):
        if not val:
            return '0'
        if hasattr(val, 'id'):
            return str(val.id)
        return str(val)
    return 'activity-{}'.format('-'.join(
        [makekey(arg) for arg in args]
    ))


def get_json_stats(request, days, step, project=None, component=None,
                   lang=None, user=None):
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
            request,
            project,
            component,
            lang
        )
        language = None
        user = None

    key = cache_key(
        days, step, project, component, translation, language, user
    )
    result = cache.get(key)
    if not result or True:
        # Get actual stats
        result = Change.objects.base_stats(
            days, step, project, component, translation, language, user
        )
        cache.set(key, result, 3600 * 4)
    return result


def yearly_activity(request, project=None, component=None, lang=None,
                    user=None):
    """Return yearly activity for matching changes as json."""
    activity = get_json_stats(
        request, 364, 7,
        project, component, lang, user,
    )

    # Format
    serie = []
    labels = []
    month = -1
    for item in activity:
        serie.append(item[1])
        if month != item[0].month:
            labels.append(
                pgettext(
                    'Format string for yearly activity chart',
                    '{month}/{year}'
                ).format(
                    month=item[0].month,
                    year=item[0].year,
                )
            )
            month = item[0].month
        else:
            labels.append('')

    return JsonResponse(
        data={'series': [serie], 'labels': labels}
    )


def monthly_activity(request, project=None, component=None, lang=None,
                     user=None):
    """Return monthly activity for matching changes as json."""
    activity = get_json_stats(
        request, 31, 1,
        project, component, lang, user
    )

    # Format
    serie = []
    labels = []
    for pos, item in enumerate(activity):
        serie.append(item[1])
        if pos % 5 == 0:
            labels.append(
                pgettext(
                    'Format string for monthly activity chart',
                    '{day}/{month}'
                ).format(
                    day=item[0].day,
                    month=item[0].month,
                    year=item[0].year,
                )
            )
        else:
            labels.append('')

    return JsonResponse(
        data={'series': [serie], 'labels': labels}
    )
