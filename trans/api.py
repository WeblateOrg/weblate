from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseNotAllowed, HttpResponseNotFound, HttpResponseBadRequest
from trans.models import Project, SubProject, Translation, Unit, Suggestion, Check
from django.shortcuts import get_object_or_404

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
