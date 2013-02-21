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

from weblate import appsettings
from django.http import HttpResponse, Http404
from django.template import RequestContext
from django.shortcuts import render_to_response
from django.utils.translation import ugettext_lazy
import django.utils.translation
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.views.decorators.cache import cache_page

from trans.models import Project
from lang.models import Language
from trans.forms import EnageLanguageForm
from trans.views.helper import get_project

import cairo
import pango
import pangocairo
from cStringIO import StringIO
import os.path

WIDGETS = {
    '287x66': {
        'default': 'grey',
        'colors': {
            'grey': {
                'bar': (0, 67.0 / 255, 118.0 / 255),
                'border': (0, 0, 0),
                'text':  (0, 0, 0),
                'line': 0.2,
            },
            'white': {
                'bar': (0, 67.0 / 255, 118.0 / 255),
                'border': (0, 0, 0),
                'text':  (0, 0, 0),
                'line': 0.2,
            },
            'black': {
                'bar': (0, 67.0 / 255, 118.0 / 255),
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
                'font': "Sans Bold",
                'font_size': 10,
                'pos': (72, 6),
            },
            {
                # Translators: text in the engagement widget
                'text': ugettext_lazy("translating %(count)d strings into %(languages)d languages\n%(percent)d%% complete, help us improve!"),
                # Translators: text in the engagement widget, please use your language name instead of English
                'text_lang': ugettext_lazy("translating %(count)d strings into English\n%(percent)d%% complete, help us improve!"),
                'font': "Sans",
                'font_size': 8,
                'pos': (72, 22),
            },
        ],
    },
    '88x31': {
        'default': 'grey',
        'colors': {
            'grey': {
                'bar': (0, 67.0 / 255, 118.0 / 255),
                'border': (0, 0, 0),
                'text':  (0, 0, 0),
                'line': 0.2,
            },
            'white': {
                'bar': (0, 67.0 / 255, 118.0 / 255),
                'border': (0, 0, 0),
                'text':  (0, 0, 0),
                'line': 0.2,
            },
            'black': {
                'bar': (0, 67.0 / 255, 118.0 / 255),
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
                'font': "Sans Bold",
                'font_size': 7,
                'pos': (23, 2),
            },
            {
                # Translators: text in the engagement widget
                'text': ugettext_lazy('translation\n%(percent)d%% done'),
                # Translators: text in the engagement widget, please use your language name instead of English
                'text_lang': ugettext_lazy('English translation\n%(percent)d%% done'),
                'font': "Sans",
                'font_size': 7,
                'pos': (23, 11),
            },
        ],
    }
}


def widgets_root(request):
    return render_to_response('widgets-root.html', RequestContext(request, {
        'projects': Project.objects.all_acl(request.user),
    }))


def widgets(request, project):
    obj = get_project(request, project)

    # Parse possible language selection
    form = EnageLanguageForm(obj, request.GET)
    lang = None
    if form.is_valid():
        if form.cleaned_data['lang'] != '':
            lang = Language.objects.get(code=form.cleaned_data['lang'])

    site = Site.objects.get_current()
    if lang is None:
        engage_base = reverse('engage', kwargs={'project': obj.slug})
    else:
        engage_base = reverse(
            'engage-lang',
            kwargs={'project': obj.slug, 'lang': lang.code}
        )
    engage_url = 'http://%s%s' % (
        site.domain,
        engage_base,
    )
    engage_url_track = '%s?utm_source=widget' % engage_url
    widget_base_url = 'http://%s%s' % (
        site.domain,
        reverse('widgets', kwargs={'project': obj.slug}),
    )
    widget_list = []
    for widget_name in WIDGETS:
        widget = WIDGETS[widget_name]
        color_list = []
        for color in widget['colors']:
            if lang is None:
                color_url = reverse(
                    'widget-image',
                    kwargs={
                        'project': obj.slug,
                        'widget': widget_name,
                        'color': color,
                    }
                )
            else:
                color_url = reverse(
                    'widget-image-lang',
                    kwargs={
                        'project': obj.slug,
                        'widget': widget_name,
                        'color': color,
                        'lang': lang.code
                    }
                )
            color_list.append({
                'name': color,
                'url': 'http://%s%s' % (
                    site.domain,
                    color_url,
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
        'form': form,
    }))


def render_text(pangocairo_context, line, text, params, font_size):
    '''
    Generates Pango layout for text.
    '''
    # Create pango layout and set font
    layout = pangocairo_context.create_layout()
    font = pango.FontDescription('%s %d' % (line['font'], font_size))
    layout.set_font_description(font)

    # Add text
    layout.set_text(text)

    return layout


@cache_page(3600)
def render(request, project, widget='287x66', color=None, lang=None):
    obj = get_project(request, project)

    # Handle language parameter
    if lang is not None:
        try:
            django.utils.translation.activate(lang)
        except:
            # Ignore failure on activating language
            pass
        try:
            lang = Language.objects.get(code=lang)
        except Language.DoesNotExist:
            lang = None

    percent = obj.get_translated_percent(lang)

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
        os.path.join(appsettings.WEB_ROOT, 'media', widget_data['name'] % {
            'color': color,
            'widget': widget,
        })
    )
    ctx = cairo.Context(surface)

    # Setup
    ctx.set_line_width(widget_data['colors'][color]['line'])

    # Progress bar rendering
    if widget_data['progress'] is not None:
        # Filled bar
        ctx.new_path()
        ctx.set_source_rgb (*widget_data['colors'][color]['bar'])
        if widget_data['progress']['horizontal']:
            ctx.rectangle(
                widget_data['progress']['x'],
                widget_data['progress']['y'],
                widget_data['progress']['width'] / 100.0 * percent,
                widget_data['progress']['height']
            )
        else:
            diff = widget_data['progress']['height'] / 100.0 * (100 - percent)
            ctx.rectangle(
                widget_data['progress']['x'],
                widget_data['progress']['y'] + diff,
                widget_data['progress']['width'],
                widget_data['progress']['height'] - diff
            )
        ctx.fill()

        # Progress border
        ctx.new_path()
        ctx.set_source_rgb(*widget_data['colors'][color]['border'])
        ctx.rectangle(
            widget_data['progress']['x'],
            widget_data['progress']['y'],
            widget_data['progress']['width'],
            widget_data['progress']['height']
        )
        ctx.stroke()

    # Text rendering
    # Set text color
    ctx.set_source_rgb(*widget_data['colors'][color]['text'])

    # Create pango context
    pangocairo_context = pangocairo.CairoContext(ctx)
    pangocairo_context.set_antialias(cairo.ANTIALIAS_SUBPIXEL)

    # Text format strings
    params =  {
        'name': obj.name,
        'count': obj.get_total(),
        'languages': obj.get_language_count(),
        'percent': percent,
    }

    for line in widget_data['text']:
        # Format text
        text = line['text']
        if lang is not None and 'text_lang' in line:
            text = line['text_lang']
            if 'English' in text:
                text = text.replace('English', lang.name)
        text = text % params

        font_size = line['font_size']

        # Render text
        layout = render_text(pangocairo_context, line, text, params, font_size)

        # Fit text to image if it is too big
        extent = layout.get_pixel_extents()
        width = surface.get_width()
        while extent[1][2] + line['pos'][0] > width and font_size > 4:
            font_size -= 1
            layout = render_text(
                pangocairo_context,
                line,
                text,
                params,
                font_size
            )
            extent = layout.get_pixel_extents()

        # Set position
        ctx.move_to(*line['pos'])

        # Render to cairo context
        pangocairo_context.update_layout(layout)
        pangocairo_context.show_layout(layout)

    # Render PNG
    out = StringIO()
    surface.write_to_png(out)
    data = out.getvalue()

    return HttpResponse(content_type='image/png', content=data)
