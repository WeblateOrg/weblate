# -*- coding: utf-8 -*-
#
# Copyright © 2012 Michal Čihař <michal@cihar.com>
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

from django.conf import settings
from django.http import HttpResponse, Http404
from django.template import RequestContext
from django.shortcuts import render_to_response, get_object_or_404
from django.utils.translation import ugettext_lazy
import django.utils.translation
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.views.decorators.cache import cache_page

from weblate.trans.models import Project

import cairo
from cStringIO import StringIO
import os.path

WIDGETS = {
    '287x66': {
        'default': 'grey',
        'colors': {
            'grey': {
                'bar': (0, 67.0/255, 118.0/255),
                'border': (0, 0, 0),
                'text':  (0, 0, 0),
                'line': 0.2,
            },
            'white': {
                'bar': (0, 67.0/255, 118.0/255),
                'border': (0, 0, 0),
                'text':  (0, 0, 0),
                'line': 0.2,
            },
            'black': {
                'bar': (0, 67.0/255, 118.0/255),
                'border': (255, 255, 255),
                'text':  (255, 255, 255),
                'line': 0.8,
            },
        },
        'name': 'weblate-widget-%(color)s.png',
        'progress': {
            'x': 72,
            'y': 52,
            'height': 6,
            'width': 180,
            'horizontal': True,
        },
        'text': [
            {
                'text': "%(name)s",
                'font': ("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD),
                'font_size': 14,
                'pos': (72, 19),
            },
            {
                # Translators: line of text in engagement widget
                'text': ugettext_lazy("translating %(count)d strings into %(languages)d languages"),
                'font': ("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL),
                'font_size': 10,
                'pos': (72, 32),
            },
            {
                # Translators: line of text in engagement widget
                'text': ugettext_lazy('%(percent)d%% complete, help us improve!'),
                'font': ("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL),
                'font_size': 10,
                'pos': (72, 44),
            },


        ],
    },
    '88x31': {
        'default': 'grey',
        'colors': {
            'grey': {
                'bar': (0, 67.0/255, 118.0/255),
                'border': (0, 0, 0),
                'text':  (0, 0, 0),
                'line': 0.2,
            },
            'white': {
                'bar': (0, 67.0/255, 118.0/255),
                'border': (0, 0, 0),
                'text':  (0, 0, 0),
                'line': 0.2,
            },
            'black': {
                'bar': (0, 67.0/255, 118.0/255),
                'border': (255, 255, 255),
                'text':  (255, 255, 255),
                'line': 0.8,
            },
        },
        'name': 'weblate-widget-%(widget)s-%(color)s.png',
        'progress': None,
        'text': [
            {
                'text': "%(name)s",
                'font': ("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD),
                'font_size': 10,
                'pos': (23, 10),
            },
            {
                # Translators: line of text in engagement widget
                'text': ugettext_lazy('translation'),
                'font': ("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL),
                'font_size': 10,
                'pos': (23, 19),
            },
            {
                # Translators: line of text in engagement widget
                'text': ugettext_lazy('%(percent)d%% done'),
                'font': ("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL),
                'font_size': 10,
                'pos': (23, 28),
            },


        ],
    }
}

def widgets(request, project):
    obj = get_object_or_404(Project, slug = project)
    site = Site.objects.get_current()
    engage_url = 'http://%s%s' % (
        site.domain,
        reverse('weblate.trans.views.show_engage', kwargs = {'project': obj.slug}),
    )
    engage_url_track = 'http://%s%s?utm_source=widget' % (
        site.domain,
        reverse('weblate.trans.views.show_engage', kwargs = {'project': obj.slug}),
    )
    widget_base_url = 'http://%s%s' % (
        site.domain,
        reverse('weblate.trans.widgets.widgets', kwargs = {'project': obj.slug}),
    )
    widget_list = []
    for widget_name in WIDGETS:
        widget = WIDGETS[widget_name]
        color_list = []
        for color in widget['colors']:
            color_list.append({
                'name': color,
                'url': 'http://%s%s' % (
                    site.domain,
                    reverse('widget-image', kwargs = {'project': obj.slug, 'widget': widget_name, 'color': color})
                ),
            })
        widget_list.append({
            'name': widget_name,
            'colors': color_list,
        })

    return render_to_response('widgets.html', RequestContext(request, {
        'engage_url': engage_url,
        'engage_url_track': engage_url_track,
        'widget_list': widget_list,
        'widget_base_url': widget_base_url,
        'object': obj,
        'image_src': widget_list[0]['colors'][0]['url'],
    }))

@cache_page(3600)
def render(request, project, widget = '287x66', color = None):
    obj = get_object_or_404(Project, slug = project)
    percent = obj.get_translated_percent()

    # Possibly activate chosen language
    if 'lang' in request.GET:
        django.utils.translation.activate(request.GET['lang'])

    # Get widget data
    try:
        widget_data = WIDGETS[widget]
    except KeyError:
        raise Http404()

    # Get widget color
    if color not in widget_data['colors']:
        color = widget_data['default']

    # Background 287 x 66, logo 64 px
    surface = cairo.ImageSurface.create_from_png(
        os.path.join(settings.WEB_ROOT, 'media', widget_data['name'] % {
            'color': color,
            'widget': widget,
        })
    )
    ctx = cairo.Context(surface)

    # Setup
    ctx.set_line_width(widget_data['colors'][color]['line'])

    # Progress bar
    if widget_data['progress'] is not None:
        # Filled bar
        ctx.new_path()
        ctx.set_source_rgb (*widget_data['colors'][color]['bar'])
        if widget_data['progress']['horizontal']:
            ctx.rectangle(widget_data['progress']['x'], widget_data['progress']['y'], widget_data['progress']['width'] / 100.0 * percent, widget_data['progress']['height'])
        else:
            diff = widget_data['progress']['height'] / 100.0 * (100 - percent)
            ctx.rectangle(widget_data['progress']['x'], widget_data['progress']['y'] + diff, widget_data['progress']['width'], widget_data['progress']['height'] - diff)
        ctx.fill()

        # Progress border
        ctx.new_path()
        ctx.set_source_rgb (*widget_data['colors'][color]['border'])
        ctx.rectangle(widget_data['progress']['x'], widget_data['progress']['y'], widget_data['progress']['width'], widget_data['progress']['height'])
        ctx.stroke()

    # Text
    ctx.set_source_rgb (*widget_data['colors'][color]['text'])
    ctx.new_path()

    for line in widget_data['text']:
        ctx.move_to(*line['pos'])
        ctx.select_font_face(*line['font'])
        ctx.set_font_size(line['font_size'])
        ctx.text_path(line['text'] % {
            'name': obj.name,
            'count': obj.get_total(),
            'languages': obj.get_language_count(),
            'percent': percent,
        })
    ctx.fill()

    # Render PNG
    out = StringIO()
    surface.write_to_png(out)
    data = out.getvalue()

    return HttpResponse(content_type = 'image/png', content = data)
