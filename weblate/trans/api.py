# -*- coding: utf-8 -*-
#
# Copyright 2012 Michal Čihař <michal@cihar.com>
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
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, HttpResponseNotAllowed, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.contrib.sites.models import Site

from weblate.trans.models import Project, SubProject

import json
import logging
import threading

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
