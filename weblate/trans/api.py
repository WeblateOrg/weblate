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

from weblate.trans import appsettings
from django.views.decorators.csrf import csrf_exempt
from django.http import (
    HttpResponse, HttpResponseNotAllowed, HttpResponseBadRequest
)
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
    if not appsettings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_object_or_404(SubProject, slug=subproject, project__slug=project)
    thread = threading.Thread(target=obj.do_update)
    thread.start()
    return HttpResponse('update triggered')


@csrf_exempt
def update_project(request, project):
    '''
    API hook for updating git repos.
    '''
    if not appsettings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_object_or_404(Project, slug=project)
    thread = threading.Thread(target=obj.do_update)
    thread.start()
    return HttpResponse('update triggered')


@csrf_exempt
def git_service_hook(request, service):
    '''
    Shared code between Git service hooks.

    Currently used for bitbucket_hook and github_hook, but should be usable for
    hook from other Git services (Google Code, custom coded sites, etc.) too.
    '''
    if not appsettings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    try:
        data = json.loads(request.POST['payload'])
    except (ValueError, KeyError):
        return HttpResponseBadRequest('could not parse json!')
    # Send the request data to the service handler.
    try:
        hook_helper = service + '_hook_helper'
        service_data = hook_helper(data)
    except NameError:
        logger.error('tried to call %s, but no such function exists',
                     hook_helper)
        return HttpResponseBadRequest('could not find hook handler!')
    except KeyError:
        return HttpResponseBadRequest('could not parse json!')
    service_long_name = service_data['service_long name']
    repo = service_data['repo']
    branch = service_data['branch']
    logger.info(
        'received %s notification on repository %s, branch %s',
        service_long_name, repo, branch
    )
    for obj in SubProject.objects.filter(repo=repo, branch=branch):
        logger.info('%s notification will update %s', obj)
        thread = threading.Thread(target=obj.do_update)
        thread.start()

    return HttpResponse('update triggered')


@csrf_exempt
def bitbucket_hook_helper(data):
    '''
    API to handle commit hooks from Bitbucket.
    '''
    repo = 'https://bitbucket.org/%s/%s.git' % (
        data['repository']['owner'],
        data['repository']['slug'],
    )
    branch = data['commits'][-1]['branch']

    return_data = {
        'service_long_name': 'Bitbucket',
        'repo': repo,
        'branch': branch,
    }

    return return_data


@csrf_exempt
def github_hook_helper(data):
    '''
    API to handle commit hooks from Github.
    '''
    repo = 'git://github.com/%s/%s.git' % (
        data['repository']['owner']['name'],
        data['repository']['name'],
    )
    branch = data['ref'].split('/')[-1]

    return_data = {
        'service_long_name': 'GitHub',
        'repo': repo,
        'branch': branch,
    }

    return return_data


def dt_handler(obj):
    if hasattr(obj, 'isoformat'):
        return obj.isoformat()
    else:
        raise TypeError(
            'Object of type %s with value of %s is not JSON serializable' %
            (type(obj), repr(obj))
        )


def export_stats(request, project, subproject):
    '''
    Exports stats in JSON format.
    '''
    subprj = get_object_or_404(
        SubProject,
        slug=subproject,
        project__slug=project
    )
    response = []
    site = Site.objects.get_current()
    for trans in subprj.translation_set.all():
        response.append({
            'code': trans.language.code,
            'name': trans.language.name,
            'total': trans.total,
            'last_change': trans.get_last_change(),
            'last_author': trans.get_last_author(False),
            'translated': trans.translated,
            'translated_percent': trans.get_translated_percent(),
            'fuzzy': trans.fuzzy,
            'fuzzy_percent': trans.get_fuzzy_percent(),
            'failing': trans.get_failing_checks(),
            'failing_percent': trans.get_failing_checks_percent(),
            'url': trans.get_share_url(),
            'url_translate': 'http://%s%s' % (
                site.domain, trans.get_absolute_url()
            ),
        })
    return HttpResponse(
        json.dumps(response, default=dt_handler),
        mimetype='application/json'
    )
