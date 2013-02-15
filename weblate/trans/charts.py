# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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

from weblate.trans.models import Change, Project, SubProject, Translation
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.http import HttpResponse
from cStringIO import StringIO
from django.core.urlresolvers import reverse
import cairo
import pycha.bar


def render_activity(ticks, line, maximum):
    '''
    Helper for rendering activity charts.
    '''

    # Prepare cairo surface
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 800, 100)

    # Data set
    data = (
        ('lines', line),
    )

    # Chart options
    options = {
        'axis': {
            'x': {
                'ticks': ticks,
            },
            'y': {
                'ticks': [
                    {'v': 0, 'label': 0}, {'v': maximum, 'label': maximum}
                ],
            }
        },
        'background': {
            'color': '#eeeeff',
            'lineColor': '#444444'
        },
        'colorScheme': {
            'name': 'gradient',
            'args': {
                'initialColor': '#004276',
            },
        },
        'legend': {
            'hide': True,
        },
    }

    # Render chart into surface
    chart = pycha.bar.VerticalBarChart(surface, options)
    chart.addDataset(data)
    chart.render()

    # Render surface to PNG
    out = StringIO()
    surface.write_to_png(out)
    data = out.getvalue()

    # Return response
    return HttpResponse(content_type='image/png', content=data)


def get_translation(project=None, subproject=None, lang=None):
    '''
    Returns project, subproject, translation tuple for given parameters.
    '''

    if lang is not None:
        # Language defined? We can get all
        translation = get_object_or_404(
            Translation,
            language__code=lang,
            subproject__slug=subproject,
            subproject__project__slug=project,
            enabled=True
        )
        subproject = translation.subproject
        project = subproject.project
    else:
        translation = None
        if subproject is not None:
            # Subproject defined?
            subproject = get_object_or_404(
                SubProject,
                project__slug=project,
                slug=subproject
            )
            project = subproject.project
        elif project is not None:
            # Only project defined?
            project = get_object_or_404(Project, slug=project)

    # Return tuple
    return project, subproject, translation


def monthly_activity(request, project=None, subproject=None, lang=None):
    '''
    Show monthly activity chart.
    '''

    # Process parameters
    project, subproject, translation = get_translation(
        project,
        subproject,
        lang
    )

    # Get actual stats
    changes_counts = Change.objects.month_stats(
        project,
        subproject,
        translation
    )

    # Preprocess data for chart
    line = [(i, l[1]) for i, l in enumerate(changes_counts)]
    maximum = max([l[1] for l in changes_counts])
    ticks = [{'v': i, 'label': l[0].day}
                for i, l in enumerate(changes_counts)]

    # Render chart
    return render_activity(ticks, line, maximum)


def yearly_activity(request, project=None, subproject=None, lang=None):
    '''
    Show yearly activity chart.
    '''

    # Process parameters
    project, subproject, translation = get_translation(
        project,
        subproject,
        lang
    )

    # Get actual stats
    changes_counts = Change.objects.year_stats(
        project,
        subproject,
        translation
    )

    # Preprocess data for chart
    line = [(i, l[1]) for i, l in enumerate(changes_counts)]
    maximum = max([l[1] for l in changes_counts])
    ticks = [{'v': i, 'label': l[0].isocalendar()[1]}
                for i, l in enumerate(changes_counts)]

    # Render chart
    return render_activity(ticks, line, maximum)


def view_activity(request, project=None, subproject=None, lang=None):
    '''
    Show html with activity charts.
    '''

    # Process parameters
    project, subproject, translation = get_translation(
        project,
        subproject,
        lang
    )

    if translation is not None:
        kwargs = {
            'project': project.slug,
            'subproject': subproject.slug,
            'lang': translation.language.code,
        }
        monthly_url = reverse(
            'monthly_activity_translation',
            kwargs=kwargs
        )
        yearly_url = reverse(
            'yearly_activity_translation',
            kwargs=kwargs
        )
    elif subproject is not None:
        kwargs = {
            'project': project.slug,
            'subproject': subproject.slug,
        }
        monthly_url = reverse(
            'monthly_activity_subproject',
            kwargs=kwargs
        )
        yearly_url = reverse(
            'yearly_activity_subproject',
            kwargs=kwargs
        )
    elif project is not None:
        kwargs = {
            'project': project.slug,
        }
        monthly_url = reverse(
            'monthly_activity_project',
            kwargs=kwargs
        )
        yearly_url = reverse(
            'yearly_activity_project',
            kwargs=kwargs
        )
    else:
        monthly_url = reverse(
            'monthly_activity',
        )
        yearly_url = reverse(
            'yearly_activity',
        )

    return render_to_response('js/activity.html', RequestContext(request, {
        'yearly_url': yearly_url,
        'monthly_url': monthly_url,
    }))
