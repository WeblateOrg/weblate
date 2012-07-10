from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.contrib.sites.models import Site

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

def widget_287(request, project):
    obj = get_object_or_404(Project, slug = project)
    percent = obj.get_translated_percent()

    response = HttpResponse(mimetype='image/png')

    # Background 287 x 66, logo 64 px
    surface = cairo.ImageSurface.create_from_png(
        os.path.join(settings.WEB_ROOT, 'media', 'weblate-widget.png')
    )
    ctx = cairo.Context(surface)

    # Setup
    ctx.set_line_width(0.2)
    ctx.select_font_face("Sans")
    ctx.set_font_size(14)

    # Progressbar params
    p_x = 72
    p_y = 52
    p_height = 6
    p_width = 180

    # Progress bar
    ctx.new_path()
    ctx.set_source_rgb (0, 67.0/255, 118.0/255)
    ctx.rectangle(p_x, p_y, p_width / 100.0 * percent, p_height)
    ctx.fill()

    # Progress border
    ctx.new_path()
    ctx.set_source_rgb (0, 0, 0)
    ctx.rectangle(p_x, p_y, p_width, p_height)
    ctx.stroke()

    # Text
    ctx.set_source_rgb (0, 0, 0)
    ctx.new_path()
    ctx.move_to(p_x, 19)
    ctx.text_path(obj.name)
    ctx.set_font_size(10)
    ctx.move_to(p_x, 32)
    ctx.text_path("translating %(count)d strings into %(languages)d languages" % {
        'count': obj.get_total(),
        'languages': obj.get_language_count(),
        'percent': percent,
    })
    ctx.move_to(p_x, 44)
    ctx.text_path('%(percent)d%% complete, help us improve!' % {
        'count': obj.get_total(),
        'languages': obj.get_language_count(),
        'percent': percent,
    })
    ctx.fill()

    surface.write_to_png(response)
    return response
