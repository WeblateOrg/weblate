from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.contrib.sites.models import Site

from weblate.trans.models import Project, SubProject

import json
import logging

logger = logging.getLogger('weblate')

@csrf_exempt
def update_subproject(request, project, subproject):
    '''
    API hook for updating git repos.
    '''
    if not settings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_object_or_404(SubProject, slug = subproject, project__slug = project)
    obj.do_update()
    return HttpResponse('updated')

@csrf_exempt
def update_project(request, project):
    '''
    API hook for updating git repos.
    '''
    if not settings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_object_or_404(Project, slug = project)
    obj.do_update()
    return HttpResponse('updated')


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
    for s in SubProject.objects.filter(repo = repo, branch = branch):
        logger.info('GitHub notification will update %s', s)
        s.do_update()

    return HttpResponse('updated')

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
