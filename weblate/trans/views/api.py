# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import csv
import json
import re
import sys
import threading

import six

from django.conf import settings
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import (
    HttpResponse, HttpResponseNotAllowed, HttpResponseBadRequest,
    JsonResponse,
)

from weblate.trans.models import SubProject
from weblate.trans.views.helper import get_project, get_subproject
from weblate.trans.stats import get_project_stats
from weblate.utils.errors import report_error
from weblate.logger import LOGGER


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

BITBUCKET_REPOS = (
    'ssh://git@bitbucket.org/%(full_name)s.git',
    'git@bitbucket.org:%(full_name)s.git',
    'https://bitbucket.org/%(full_name)s.git',
    'https://bitbucket.org/%(full_name)s',
    'ssh://hg@bitbucket.org/%(full_name)s',
    'hg::ssh://hg@bitbucket.org/%(full_name)s',
    'hg::https://bitbucket.org/%(full_name)s',
)

GITHUB_REPOS = (
    'git://github.com/%(owner)s/%(slug)s.git',
    'https://github.com/%(owner)s/%(slug)s.git',
    'https://github.com/%(owner)s/%(slug)s',
    'git@github.com:%(owner)s/%(slug)s.git',
)

HOOK_HANDLERS = {}


def hook_response(response='Update triggered', status='success'):
    """Generic okay hook response"""
    return JsonResponse(
        data={'status': status, 'message': response},
    )


def register_hook(handler):
    """Register hook handler."""
    name = handler.__name__.split('_')[0]
    HOOK_HANDLERS[name] = handler
    return handler


def perform_update(obj):
    """Trigger update of given object."""
    if settings.BACKGROUND_HOOKS:
        thread = threading.Thread(target=obj.do_update)
        thread.start()
    else:
        obj.do_update()


@csrf_exempt
def update_subproject(request, project, subproject):
    """API hook for updating git repos."""
    if not settings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_subproject(request, project, subproject, True)
    if not obj.project.enable_hooks:
        return HttpResponseNotAllowed([])
    perform_update(obj)
    return hook_response()


@csrf_exempt
def update_project(request, project):
    """API hook for updating git repos."""
    if not settings.ENABLE_HOOKS:
        return HttpResponseNotAllowed([])
    obj = get_project(request, project, True)
    if not obj.enable_hooks:
        return HttpResponseNotAllowed([])
    perform_update(obj)
    return hook_response()


def parse_hook_payload(request):
    """Parse hook payload."""
    # GitLab sends json as application/json
    if request.META['CONTENT_TYPE'] == 'application/json':
        return json.loads(request.body.decode('utf-8'))
    # Bitbucket and GitHub sends json as x-www-form-data
    else:
        return json.loads(request.POST['payload'])


@require_POST
@csrf_exempt
def vcs_service_hook(request, service):
    """Shared code between VCS service hooks.

    Currently used for bitbucket_hook, github_hook and gitlab_hook, but should
    be usable for other VCS services (Google Code, custom coded sites, etc.)
    too.
    """
    # We support only post methods
    if not settings.ENABLE_HOOKS:
        return HttpResponseNotAllowed(())

    # Check if we got payload
    try:
        data = parse_hook_payload(request)
    except (ValueError, KeyError, UnicodeError):
        return HttpResponseBadRequest('Could not parse JSON payload!')

    # Get service helper
    hook_helper = HOOK_HANDLERS[service]

    # Send the request data to the service handler.
    try:
        service_data = hook_helper(data)
    except Exception as error:
        LOGGER.error('failed to parse service %s data', service)
        report_error(error, sys.exc_info())
        return HttpResponseBadRequest('Invalid data in json payload!')

    # Log data
    service_long_name = service_data['service_long_name']
    repos = service_data['repos']
    repo_url = service_data['repo_url']
    branch = service_data['branch']

    # Generate filter
    spfilter = Q(repo__in=repos)

    # We need to match also URLs which include username and password
    for repo in repos:
        if not repo.startswith('https://'):
            continue
        spfilter = spfilter | (
            Q(repo__startswith='https://') &
            Q(repo__endswith='@{0}'.format(repo[8:]))
        )

    all_subprojects = SubProject.objects.filter(spfilter)

    if branch is not None:
        all_subprojects = all_subprojects.filter(branch=branch)

    subprojects = all_subprojects.filter(project__enable_hooks=True)

    LOGGER.info(
        'received %s notification on repository %s, branch %s,'
        '%d matching components, %d to process',
        service_long_name, repo_url, branch,
        all_subprojects.count(), subprojects.count(),
    )

    # Trigger updates
    updates = 0
    for obj in subprojects:
        updates += 1
        LOGGER.info(
            '%s notification will update %s',
            service_long_name,
            obj
        )
        perform_update(obj)

    if updates == 0:
        return hook_response('No matching repositories found!', 'failure')

    return hook_response()


def bitbucket_webhook_helper(data):
    """API to handle webhooks from Bitbucket"""
    repos = [
        repo % {'full_name': data['repository']['full_name']}
        for repo in BITBUCKET_REPOS
    ]

    branch = None

    changes = data['push']['changes']

    if changes:
        if changes[-1]['new']:
            branch = changes[-1]['new']['name']
        elif changes[-1]['old']:
            branch = changes[-1]['old']['name']

    return {
        'service_long_name': 'Bitbucket',
        'repo_url': data['repository']['links']['html']['href'],
        'repos': repos,
        'branch': branch,
    }


@register_hook
def bitbucket_hook_helper(data):
    """API to handle service hooks from Bitbucket."""
    if 'push' in data:
        return bitbucket_webhook_helper(data)

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
        LOGGER.error(
            'unsupported repository: %s',
            repr(data['repository'])
        )
        raise ValueError('unsupported repository')

    return {
        'service_long_name': 'Bitbucket',
        'repo_url': ''.join([
            data['canon_url'], data['repository']['absolute_url']
        ]),
        'repos': repos,
        'branch': branch,
    }


@register_hook
def github_hook_helper(data):
    """API to handle commit hooks from GitHub."""
    # Parse owner, branch and repository name
    owner = data['repository']['owner']['name']
    slug = data['repository']['name']
    branch = re.sub(r'^refs/heads/', '', data['ref'])

    params = {'owner': owner, 'slug': slug}

    # Construct possible repository URLs
    repos = [repo % params for repo in GITHUB_REPOS]

    return {
        'service_long_name': 'GitHub',
        'repo_url': data['repository']['url'],
        'repos': repos,
        'branch': branch,
    }


@register_hook
def gitlab_hook_helper(data):
    """API to handle commit hooks from GitLab."""
    ssh_url = data['repository']['url']
    http_url = '.'.join((data['repository']['homepage'], 'git'))
    branch = re.sub(r'^refs/heads/', '', data['ref'])

    # Construct possible repository URLs
    repos = [
        ssh_url,
        http_url,
        data['repository']['git_http_url'],
        data['repository']['git_ssh_url'],
    ]

    return {
        'service_long_name': 'GitLab',
        'repo_url': data['repository']['homepage'],
        'repos': repos,
        'branch': branch,
    }


def export_stats_project(request, project):
    """Export stats in JSON format."""
    obj = get_project(request, project)

    data = get_project_stats(obj)
    return export_response(
        request,
        'stats-{0}.csv'.format(obj.slug),
        (
            'language',
            'code',
            'total',
            'translated',
            'translated_percent',
            'total_words',
            'translated_words',
            'words_percent',
        ),
        data
    )


def export_stats(request, project, subproject):
    """Export stats in JSON format."""
    subprj = get_subproject(request, project, subproject)

    data = [
        trans.get_stats() for trans in subprj.translation_set.all()
    ]
    return export_response(
        request,
        'stats-{0}-{1}.csv'.format(subprj.project.slug, subprj.slug),
        (
            'name',
            'code',
            'total',
            'translated',
            'translated_percent',
            'total_words',
            'translated_words',
            'failing',
            'failing_percent',
            'fuzzy',
            'fuzzy_percent',
            'url_translate',
            'url',
            'last_change',
            'last_author',
        ),
        data
    )


def export_response(request, filename, fields, data):
    """Generic handler for stats exports"""
    output = request.GET.get('format', 'json')
    if output not in ('json', 'csv'):
        output = 'json'

    if output == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename={0}'.format(
            filename
        )

        writer = csv.DictWriter(
            response, fields
        )

        writer.writeheader()
        if six.PY2:
            for row in data:
                for item in row:
                    if isinstance(row[item], six.text_type):
                        row[item] = row[item].encode('utf-8')
                writer.writerow(row)
        else:
            for row in data:
                writer.writerow(row)
        return response
    return JsonResponse(
        data=data,
        safe=False,
        json_dumps_params={'indent': 2}
    )
