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
from weblate.lang.models import Language
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.http import HttpResponse
from django.contrib.auth.models import User
from cStringIO import StringIO
from django.core.urlresolvers import reverse
import cairo
import pango
import pangocairo
import math


def render_activity(activity):
    '''
    Helper for rendering activity charts.
    '''
    # Preprocess data for chart
    maximum = max([l[1] for l in activity] + [1])
    step = 780.0 / len(activity)
    width = step / 2

    # Prepare cairo surface and context
    surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 800, 100)
    ctx = cairo.Context(surface)

    # Render background
    ctx.set_source_rgb(1, 1, 1)
    ctx.rectangle(0, 0, 800, 100)
    ctx.fill()

    # Render axises
    ctx.new_path()
    ctx.set_line_width(1)
    ctx.set_source_rgb(0, 0, 0)
    ctx.move_to(15, 5)
    ctx.line_to(15, 85)
    ctx.line_to(795, 85)
    ctx.stroke()

    # Context for text rendering
    pangocairo_context = pangocairo.CairoContext(ctx)
    pangocairo_context.set_antialias(cairo.ANTIALIAS_SUBPIXEL)
    font = pango.FontDescription('Sans 8')

    # Rotate context for vertical text
    ctx.rotate(-math.pi / 2)

    # Create Y axis label
    layout = pangocairo_context.create_layout()
    layout.set_width(80)
    layout.set_alignment(pango.ALIGN_RIGHT)
    layout.set_font_description(font)
    layout.set_text(str(maximum))

    # Render Y axis label
    ctx.move_to(-5, 0)
    ctx.set_source_rgb(0, 0, 0)
    pangocairo_context.update_layout(layout)
    pangocairo_context.show_layout(layout)

    # Rotate context back
    ctx.rotate(math.pi / 2)

    # Counter for rendering ticks
    last = -40

    # Render activity itself
    for offset, value in enumerate(activity):
        # Calculate position
        current = offset * step

        # Render bar
        ctx.new_path()
        ctx.set_source_rgb(0, 67.0 / 255, 118.0 / 255)
        ctx.rectangle(
            20 + current,
            84,
            width,
            - 1.0 - value[1] * 78.0 / maximum
        )
        ctx.fill()

        # Skip axis labels if they are too frequent
        if current < last + 40:
            continue
        last = current

        # Create text
        layout = pangocairo_context.create_layout()
        layout.set_font_description(font)
        layout.set_text(value[0].strftime('%m/%d'))

        # Render text
        ctx.move_to(15 + current, 86)
        ctx.set_source_rgb(0, 0, 0)
        pangocairo_context.update_layout(layout)
        pangocairo_context.show_layout(layout)

    # Render surface to PNG
    out = StringIO()
    surface.write_to_png(out)

    # Return response
    return HttpResponse(content_type='image/png', content=out.getvalue())


def get_translation(request, project=None, subproject=None, lang=None):
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
        translation.check_acl(request)
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
            subproject.check_acl(request)
            project = subproject.project
        elif project is not None:
            # Only project defined?
            project = get_object_or_404(Project, slug=project)
            project.check_acl(request)

    # Return tuple
    return project, subproject, translation


def monthly_activity(request, project=None, subproject=None, lang=None):
    '''
    Show monthly activity chart.
    '''

    # Process parameters
    project, subproject, translation = get_translation(
        request,
        project,
        subproject,
        lang
    )

    # Get actual stats
    activity = Change.objects.month_stats(
        project,
        subproject,
        translation
    )

    # Render chart
    return render_activity(activity)


def yearly_activity(request, project=None, subproject=None, lang=None):
    '''
    Show yearly activity chart.
    '''

    # Process parameters
    project, subproject, translation = get_translation(
        request,
        project,
        subproject,
        lang
    )

    # Get actual stats
    activity = Change.objects.year_stats(
        project,
        subproject,
        translation
    )

    # Render chart
    return render_activity(activity)


def monthly_language_activity(request, lang):
    '''
    Show monthly activity chart.
    '''

    # Process parameters
    language = get_object_or_404(Language, code=lang)

    # Get actual stats
    activity = Change.objects.month_stats(
        language=language
    )

    # Render chart
    return render_activity(activity)


def yearly_language_activity(request, lang):
    '''
    Show yearly activity chart.
    '''

    # Process parameters
    language = get_object_or_404(Language, code=lang)

    # Get actual stats
    activity = Change.objects.year_stats(
        language=language
    )

    # Render chart
    return render_activity(activity)


def monthly_user_activity(request, user):
    '''
    Show monthly activity chart.
    '''

    # Process parameters
    user = get_object_or_404(User, username=user)

    # Get actual stats
    activity = Change.objects.month_stats(
        user=user
    )

    # Render chart
    return render_activity(activity)


def yearly_user_activity(request, user):
    '''
    Show yearly activity chart.
    '''

    # Process parameters
    user = get_object_or_404(User, username=user)

    # Get actual stats
    activity = Change.objects.year_stats(
        user=user
    )

    # Render chart
    return render_activity(activity)


def view_activity(request, project=None, subproject=None, lang=None):
    '''
    Show html with activity charts.
    '''

    # Process parameters
    project, subproject, translation = get_translation(
        request,
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


def view_language_activity(request, lang):
    '''
    Show html with activity charts.
    '''

    # Process parameters
    language = get_object_or_404(Language, code=lang)

    monthly_url = reverse(
        'monthly_language_activity',
        kwargs={'lang': language.code},
    )
    yearly_url = reverse(
        'yearly_language_activity',
        kwargs={'lang': language.code},
    )

    return render_to_response('js/activity.html', RequestContext(request, {
        'yearly_url': yearly_url,
        'monthly_url': monthly_url,
    }))
