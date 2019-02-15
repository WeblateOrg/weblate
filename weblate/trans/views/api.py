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

from __future__ import absolute_import, unicode_literals

import csv

import six

from django.http import HttpResponse, JsonResponse

from weblate.utils.views import get_project, get_component
from weblate.trans.stats import get_project_stats


def export_stats_project(request, project):
    """Export stats in JSON format."""
    obj = get_project(request, project)

    data = get_project_stats(obj)
    return export_response(
        request,
        'stats-{0}.csv'.format(obj.slug),
        (
            'language',
            'code',
            'total',
            'translated',
            'translated_percent',
            'total_words',
            'translated_words',
            'words_percent',
        ),
        data
    )


def export_stats(request, project, component):
    """Export stats in JSON format."""
    subprj = get_component(request, project, component)

    data = [
        trans.get_stats() for trans in subprj.translation_set.all()
    ]
    return export_response(
        request,
        'stats-{0}-{1}.csv'.format(subprj.project.slug, subprj.slug),
        (
            'name',
            'code',
            'total',
            'translated',
            'translated_percent',
            'total_words',
            'translated_words',
            'failing',
            'failing_percent',
            'fuzzy',
            'fuzzy_percent',
            'url_translate',
            'url',
            'last_change',
            'last_author',
        ),
        data
    )


def export_response(request, filename, fields, data):
    """Generic handler for stats exports"""
    output = request.GET.get('format', 'json')
    if output not in ('json', 'csv'):
        output = 'json'

    if output == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename={0}'.format(
            filename
        )

        writer = csv.DictWriter(
            response, fields
        )

        writer.writeheader()
        if six.PY2:
            for row in data:
                for item in row:
                    if isinstance(row[item], six.text_type):
                        row[item] = row[item].encode('utf-8')
                writer.writerow(row)
        else:
            for row in data:
                writer.writerow(row)
        return response
    return JsonResponse(
        data=data,
        safe=False,
        json_dumps_params={'indent': 2}
    )
