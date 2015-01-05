# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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
from django.views.decorators.csrf import csrf_exempt
from django.http import (
    HttpResponse, HttpResponseNotAllowed, HttpResponseBadRequest
)

from weblate.trans.models import SubProject
from weblate.trans.views.helper import get_project, get_subproject
from weblate.trans.util import get_site_url

import json
import weblate
import threading
import re


BITBUCKET_GIT_REPOS = (
    'ssh://git@bitbucket.org/%(owner)s/%(slug)s.git',
    'git@bitbucket.org:%(owner)s/%(slug)s.git',
    'https://bitbucket.org/%(owner)s/%(slug)s.git',
)

BITBUCKET_HG_REPOS = (
    'https://bitbucket.org/%(owner)s/%(slug)s',
    'ssh://hg@bitbucket.org/%(owner)s/%(slug)s',
    'hg::ssh://hg@bitbucket.org/%(owner)s/%(slug)s',
    'hg::https://bitbucket.org/%(owner)s/%(slug)s',
)

GITHUB_REPOS = (
    'git://github.com/%(owner)s/%(slug)s.git',
    'https://github.com/%(owner)s/%(slug)s.git',
    'git@github.com:%(owner)s/%(slug)s.git',
)

HOOK_HANDLERS = {}


def register_hook(handler):
    """
    Registers hook handler.
    """
    name = handler.__name__.split('_')[0]
    HOOK_HANDLERS[name] = handler
    return handler


def perform_update(obj):
    '''
    Triggers update of given object.
    '''
    if appsettings.BACKGROUND_HOOKS:
        thread = threading.Thread(target=obj.do_update)
        thread.start()
    else:
        obj.do_update()


@csrf_exempt
def update_subproject(request, project, subproject):
    '''
    API hook for updating git repos.
    '''
    if not appsettings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_subproject(request, project, subproject, True)
    if not obj.project.enable_hooks:
        return HttpResponseNotAllowed([])
    perform_update(obj)
    return HttpResponse('update triggered')


@csrf_exempt
def update_project(request, project):
    '''
    API hook for updating git repos.
    '''
    if not appsettings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_project(request, project, True)
    if not obj.enable_hooks:
        return HttpResponseNotAllowed([])
    perform_update(obj)
    return HttpResponse('update triggered')


@csrf_exempt
def vcs_service_hook(request, service):
    '''
    Shared code between VCS service hooks.

    Currently used for bitbucket_hook, github_hook and gitlab_hook, but should
    be usable for other VCS services (Google Code, custom coded sites, etc.)
    too.
    '''
    # Check for enabled hooks
    if appsettings.ENABLE_HOOKS:
        allowed_methods = ('POST',)
    else:
        allowed_methods = ()

    # We support only post methods
    if not appsettings.ENABLE_HOOKS or request.method not in allowed_methods:
        return HttpResponseNotAllowed(allowed_methods)

    # Check if we got payload
    try:
        # GitLab sends json as application/json
        if request.META['CONTENT_TYPE'] == 'application/json':
            data = json.loads(request.body)
        # Bitbucket and GitHub sends json as x-www-form-data
        else:
            data = json.loads(request.POST['payload'])
    except (ValueError, KeyError):
        return HttpResponseBadRequest('Could not parse JSON payload!')

    # Get service helper
    if service not in HOOK_HANDLERS:
        weblate.logger.error('service %s is not supported', service)
        return HttpResponseBadRequest('invalid service')
    hook_helper = HOOK_HANDLERS[service]

    # Send the request data to the service handler.
    try:
        service_data = hook_helper(data)
    except KeyError:
        return HttpResponseBadRequest('Invalid data in json payload!')

    # Log data
    service_long_name = service_data['service_long_name']
    repos = service_data['repos']
    branch = service_data['branch']

    weblate.logger.info(
        'received %s notification on repository %s, branch %s',
        service_long_name, repos[0], branch
    )

    subprojects = SubProject.objects.filter(repo__in=repos)

    if branch is not None:
        subprojects = subprojects.filter(branch=branch)

    # Trigger updates
    for obj in subprojects:
        if not obj.project.enable_hooks:
            continue
        weblate.logger.info(
            '%s notification will update %s',
            service_long_name,
            obj
        )
        perform_update(obj)

    return HttpResponse('update triggered')


@register_hook
def bitbucket_hook_helper(data):
    '''
    API to handle commit hooks from Bitbucket.
    '''
    # Parse owner, branch and repository name
    owner = data['repository']['owner']
    slug = data['repository']['slug']
    if data['commits']:
        branch = data['commits'][-1]['branch']
    else:
        branch = None
    params = {'owner': owner, 'slug': slug}

    # Construct possible repository URLs
    if data['repository']['scm'] == 'git':
        repos = [repo % params for repo in BITBUCKET_GIT_REPOS]
    elif data['repository']['scm'] == 'hg':
        repos = [repo % params for repo in BITBUCKET_HG_REPOS]
    else:
        weblate.logger.error(
            'unsupported repository: %s',
            repr(data['repositoru'])
        )
        raise ValueError('unsupported repository')

    return {
        'service_long_name': 'Bitbucket',
        'repos': repos,
        'branch': branch,
    }


@register_hook
def github_hook_helper(data):
    '''
    API to handle commit hooks from GitHub.
    '''
    # Parse owner, branch and repository name
    owner = data['repository']['owner']['name']
    slug = data['repository']['name']
    branch = re.sub(r'^refs/heads/', '', data['ref'])

    # Construct possible repository URLs
    repos = [repo % {'owner': owner, 'slug': slug} for repo in GITHUB_REPOS]

    return {
        'service_long_name': 'GitHub',
        'repos': repos,
        'branch': branch,
    }


@register_hook
def gitlab_hook_helper(data):
    '''
    API to handle commit hooks from GitLab.
    '''
    ssh_url = data['repository']['url']
    http_url = '.'.join((data['repository']['homepage'], 'git'))
    branch = re.sub(r'^refs/heads/', '', data['ref'])

    # Construct possible repository URLs
    repos = [ssh_url, http_url]

    return {
        'service_long_name': 'GitLab',
        'repos': repos,
        'branch': branch,
    }


def json_dt_handler(obj):
    '''
    JSON export handler to include correctly formated datetime objects.
    '''
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
    subprj = get_subproject(request, project, subproject)

    try:
        indent = int(request.GET['indent'])
    except (ValueError, KeyError):
        indent = None

    jsonp = None
    if 'jsonp' in request.GET and request.GET['jsonp']:
        jsonp = request.GET['jsonp']

    response = []
    for trans in subprj.translation_set.all():
        response.append({
            'code': trans.language.code,
            'name': trans.language.name,
            'total': trans.total,
            'total_words': trans.total_words,
            'last_change': trans.last_change,
            'last_author': trans.get_last_author(),
            'translated': trans.translated,
            'translated_words': trans.translated_words,
            'translated_percent': trans.get_translated_percent(),
            'fuzzy': trans.fuzzy,
            'fuzzy_percent': trans.get_fuzzy_percent(),
            'failing': trans.failing_checks,
            'failing_percent': trans.get_failing_checks_percent(),
            'url': trans.get_share_url(),
            'url_translate': get_site_url(trans.get_absolute_url()),
        })
    json_data = json.dumps(
        response,
        default=json_dt_handler,
        indent=indent,
    )
    if jsonp:
        return HttpResponse(
            '{0}({1})'.format(
                jsonp,
                json_data,
            ),
            content_type='application/javascript'
        )
    return HttpResponse(
        json_data,
        content_type='application/json'
    )
