from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseBadRequest
from django.template import RequestContext
from django.shortcuts import render_to_response, get_object_or_404
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.views.decorators.cache import cache_page

from weblate.trans.models import Project, SubProject

import json
import logging
import threading
import cairo
import os.path

logger = logging.getLogger('weblate')


def widgets(request, project):
    obj = get_object_or_404(Project, slug = project)
    site = Site.objects.get_current()
    engage_url = 'http://%s%s?utm_source=widget' % (
        site.domain,
        reverse('weblate.trans.views.show_engage', kwargs = {'project': obj.slug}),
    )
    widget_base_url = 'http://%s%s' % (
        site.domain,
        reverse('weblate.trans.widgets.widgets', kwargs = {'project': obj.slug}),
    )

    widget_list = [
        '287x66',
    ]

    return render_to_response('widgets.html', RequestContext(request, {
        'engage_url': engage_url,
        'widget_list': widget_list,
        'widget_base_url': widget_base_url,
        'object': obj,
    }))

WIDGETS = {
    '287': {
        'default': 'grey',
        'colors': {
            'grey': {
                'bar': (0, 67.0/255, 118.0/255),
                'border': (0, 0, 0),
                'text':  (0, 0, 0),
            },
            'white': {
                'bar': (0, 67.0/255, 118.0/255),
                'border': (0, 0, 0),
                'text':  (0, 0, 0),
            },
            'black': {
                'bar': (0, 67.0/255, 118.0/255),
                'border': (255, 255, 255),
                'text':  (255, 255, 255),
            },
        },
        'name': 'weblate-widget-%(color)s.png',
        'progress': {
            'x': 72,
            'y': 52,
            'height': 6,
            'width': 180,
        },
        'text': [
            {
                'text': "%(name)s",
                'font': ("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL),
                'font_size': 14,
                'pos': (72, 19),
            },
            {
                'text': "translating %(count)d strings into %(languages)d languages",
                'font': ("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL),
                'font_size': 10,
                'pos': (72, 32),
            },
            {
                'text': '%(percent)d%% complete, help us improve!',
                'font': ("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL),
                'font_size': 10,
                'pos': (72, 44),
            },


        ],
    }
}

#@cache_page(3600)
def widget_287(request, project, widget = '287'):
    obj = get_object_or_404(Project, slug = project)
    percent = obj.get_translated_percent()

    widget_data = WIDGETS[widget]

    # Get widget color
    color = request.GET.get('color', widget_data['default'])
    if color not in widget_data['colors']:
        color = widget_data['default']

    response = HttpResponse(mimetype='image/png')

    # Background 287 x 66, logo 64 px
    surface = cairo.ImageSurface.create_from_png(
        os.path.join(settings.WEB_ROOT, 'media', widget_data['name'] % {'color': color})
    )
    ctx = cairo.Context(surface)

    # Setup
    ctx.set_line_width(0.2)

    # Progress bar
    ctx.new_path()
    ctx.set_source_rgb (*widget_data['colors'][color]['bar'])
    ctx.rectangle(widget_data['progress']['x'], widget_data['progress']['y'], widget_data['progress']['width'] / 100.0 * percent, widget_data['progress']['height'])
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

    surface.write_to_png(response)
    return response
