# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
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
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.models import User
from cStringIO import StringIO
from django.core.urlresolvers import reverse
from PIL import Image, ImageDraw
from weblate.trans.fonts import get_font


def render_activity(activity):
    '''
    Helper for rendering activity charts.
    '''
    # Preprocess data for chart
    maximum = max([l[1] for l in activity] + [1])
    step = 780.0 / len(activity)

    # Prepare image
    image = Image.new('RGB', (800, 100), 'white')
    draw = ImageDraw.Draw(image)

    # Render axises
    draw.line(((15, 5), (15, 85), (795, 85)), fill='black')

    # Load font
    font = get_font(11)

    # Create Y axis label
    y_label = str(maximum)
    text = Image.new('L', font.getsize(y_label), 'white')
    draw_txt = ImageDraw.Draw(text)
    draw_txt.text((0, 0), y_label, font=font, fill='black')
    text = text.transpose(Image.ROTATE_90)

    image.paste(text, (2, 5))
    # Counter for rendering ticks
    last = -40

    # Render activity itself
    for offset, value in enumerate(activity):
        # Calculate position
        current = offset * step

        # Render bar
        draw.rectangle(
            (
                20 + current,
                84,
                20 + current + (step / 2),
                84 - value[1] * 78.0 / maximum
            ),
            fill=(0, 67, 118)
        )

        # Skip axis labels if they are too frequent
        if current < last + 40:
            continue
        last = current

        # X-Axis ticks
        draw.text(
            (15 + current, 86),
            value[0].strftime('%m/%d'),
            font=font, fill='black'
        )

    # Render surface to PNG
    out = StringIO()
    image.convert('P', palette=Image.ADAPTIVE).save(out, 'PNG')

    # Return response
    return HttpResponse(content_type='image/png', content=out.getvalue())


def monthly_activity(request, project=None, subproject=None, lang=None):
    '''
    Show monthly activity chart.
    '''

    # Process parameters
    project, subproject, translation = get_project_translation(
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
    project, subproject, translation = get_project_translation(
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
    project, subproject, translation = get_project_translation(
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

    return render(
        request,
        'js/activity.html',
        {
            'yearly_url': yearly_url,
            'monthly_url': monthly_url,
        }
    )


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

    return render(
        request,
        'js/activity.html',
        {
            'yearly_url': yearly_url,
            'monthly_url': monthly_url,
        }
    )
