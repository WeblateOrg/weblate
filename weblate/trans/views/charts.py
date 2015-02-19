# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
'''
Charting library for Weblate.
'''

from weblate.trans.models import Change
from weblate.lang.models import Language
from weblate.trans.views.helper import get_project_translation
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.models import User
from django.utils.translation import pgettext
import json


def get_json_stats(request, days, step, project=None, subproject=None,
                   lang=None, user=None):
    """
    Parse json stats URL params.
    """
    if project is None and lang is None and user is None:
        project = None
        subproject = None
        translation = None
        language = None
        user = None
    elif user is not None:
        project = None
        subproject = None
        translation = None
        language = None
        user = get_object_or_404(User, username=user)
    elif project is None:
        project = None
        subproject = None
        translation = None
        language = get_object_or_404(Language, code=lang)
        user = None
    else:
        # Process parameters
        project, subproject, translation = get_project_translation(
            request,
            project,
            subproject,
            lang
        )
        language = None
        user = None

    # Get actual stats
    return Change.objects.base_stats(
        days,
        step,
        project,
        subproject,
        translation,
        language,
        user
    )


def yearly_activity(request, project=None, subproject=None, lang=None,
                    user=None):
    """
    Returns yearly activity for matching changes as json.
    """
    activity = get_json_stats(
        request, 364, 7,
        project, subproject, lang
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

    return HttpResponse(
        content_type='application/json',
        content=json.dumps({'series': [serie], 'labels': labels})
    )


def monthly_activity(request, project=None, subproject=None, lang=None,
                     user=None):
    """
    Returns monthly activity for matching changes as json.
    """
    activity = get_json_stats(
        request, 31, 1,
        project, subproject, lang
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

    return HttpResponse(
        content_type='application/json',
        content=json.dumps({'series': [serie], 'labels': labels})
    )
