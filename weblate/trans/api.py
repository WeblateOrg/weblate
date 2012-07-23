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

@csrf_exempt
def update_subproject(request, project, subproject):
    '''
    API hook for updating git repos.
    '''
    if not settings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)
    t = threading.Thread(target = obj.do_update)
    t.start()
    return HttpResponse('update triggered')

@csrf_exempt
def update_project(request, project):
    '''
    API hook for updating git repos.
    '''
    if not settings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_object_or_404(Project, slug = project)
    t = threading.Thread(target = obj.do_update)
    t.start()
    return HttpResponse('update triggered')


@csrf_exempt
def github_hook(request):
    '''
    API to handle commit hooks from Github.
    '''
    if not settings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    try:
        data = json.loads(request.POST['payload'])
    except (ValueError, KeyError):
        return HttpResponseBadRequest('could not parse json!')
    repo = 'git://github.com/%s/%s.git' % (
        data['repository']['owner']['name'],
        data['repository']['name'],
        )
    branch = data['ref'].split('/')[-1]
    logger.info('received GitHub notification on repository %s, branch %s', repo, branch)
    for obj in SubProject.objects.filter(repo = repo, branch = branch):
        logger.info('GitHub notification will update %s', obj)
        t = threading.Thread(target = obj.do_update)
        t.start()

    return HttpResponse('update triggered')

def dt_handler(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    else:
        raise TypeError('Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj)))

def export_stats(request, project, subproject):
    '''
    Exports stats in JSON format.
    '''
    subprj = get_object_or_404(SubProject, slug = subproject, project__slug = project)
    response = []
    site = Site.objects.get_current()
    for trans in subprj.translation_set.all():
        response.append({
            'code': trans.language.code,
            'name': trans.language.name,
            'total': trans.total,
            'fuzzy': trans.fuzzy,
            'last_change': trans.get_last_change(),
            'last_author': trans.get_last_author(False),
            'translated': trans.translated,
            'translated_percent': trans.get_translated_percent(),
            'fuzzy_percent': trans.get_fuzzy_percent(),
            'url': 'http://%s%s' % (site.domain, trans.get_absolute_url()),
        })
    return HttpResponse(
        json.dumps(response, default = dt_handler),
        mimetype = 'application/json'
    )

def widgets(request, project):
    obj = get_object_or_404(Project, slug = project)
    site = Site.objects.get_current()
    engage_url = 'http://%s%s?utm_source=widget' % (
        site.domain,
        reverse('weblate.trans.views.show_engage', kwargs = {'project': obj.slug}),
    )
    widget_base_url = 'http://%s%s' % (
        site.domain,
        reverse('weblate.trans.api.widgets', kwargs = {'project': obj.slug}),
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
