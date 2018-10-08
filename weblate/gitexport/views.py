# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from base64 import b64decode
from email import message_from_string
import os.path
import subprocess

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.http.response import HttpResponseServerError, HttpResponse
from django.shortcuts import redirect
from django.utils.encoding import force_text
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache

from weblate.auth.models import User
from weblate.utils.errors import report_error
from weblate.utils.views import get_component


GIT_PATHS = [
    '/usr/lib/git',
    '/usr/lib/git-core',
]


def find_git_http_backend():
    """Find git http backend"""

    if hasattr(find_git_http_backend, 'result'):
        return find_git_http_backend.result

    try:
        path = subprocess.check_output(['git', '--exec-path']).decode('utf-8')
        if path:
            GIT_PATHS.insert(0, path)
    except OSError:
        pass

    for path in GIT_PATHS:
        name = os.path.join(path, 'git-http-backend')
        if os.path.exists(name):
            find_git_http_backend.result = name
            return name
    return None


def response_authenticate():
    """Return 401 response with authenticate header."""
    response = HttpResponse(status=401)
    response['WWW-Authenticate'] = 'Basic realm="Weblate Git access"'
    return response


def authenticate(request, auth):
    """Perform authentication with HTTP Basic auth"""
    auth = force_text(auth, encoding='iso-8859-1')
    try:
        method, data = auth.split(None, 1)
        if method.lower() == 'basic':
            username, code = b64decode(data).decode('iso-8859-1').split(':', 1)
            try:
                user = User.objects.get(
                    username=username,
                    auth_token__key=code
                )
            except User.DoesNotExist:
                return False

            if not user.is_active:
                return False

            request.user = user
            return True
        else:
            return False
    except (ValueError, TypeError):
        return False


@never_cache
@csrf_exempt
def git_export(request, project, component, path):
    """Git HTTP server view.

    Wrapper around git-http-backend to provide Git repositories export over
    HTTP. Performs permission checks and hands over execution to the wrapper.
    """
    # Probably browser access
    if not path:
        return redirect(
            'component',
            project=project,
            component=component,
            permanent=False
        )
    # Strip possible double path separators
    path = path.lstrip('/\\')

    # HTTP authentication
    auth = request.META.get('HTTP_AUTHORIZATION', b'')

    # Reject non pull access early
    if request.GET.get('service', '') not in ('', 'git-upload-pack'):
        raise PermissionDenied('Only pull is supported')

    if auth and not authenticate(request, auth):
        return response_authenticate()

    # Permissions
    try:
        obj = get_component(request, project, component)
    except Http404:
        if not request.user.is_authenticated:
            return response_authenticate()
        raise
    if not request.user.has_perm('vcs.access', obj):
        raise PermissionDenied('No VCS permissions')

    return run_git_http(request, obj, path)


def run_git_http(request, obj, path):
    """Git HTTP backend execution wrapper."""
    # Find Git HTTP backend
    git_http_backend = find_git_http_backend()
    if git_http_backend is None:
        return HttpResponseServerError('git-http-backend not found')

    # Invoke Git HTTP backend
    query = request.META.get('QUERY_STRING', '')
    process_env = {
        'REQUEST_METHOD': request.method,
        'PATH_TRANSLATED': os.path.join(obj.full_path, path),
        'GIT_HTTP_EXPORT_ALL': '1',
        'CONTENT_TYPE': request.META.get('CONTENT_TYPE', ''),
        'QUERY_STRING': query,
        'HTTP_CONTENT_ENCODING': request.META.get('HTTP_CONTENT_ENCODING', ''),
    }
    process = subprocess.Popen(
        [git_http_backend],
        env=process_env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    output, output_err = process.communicate(request.body)
    retcode = process.poll()

    # Log error
    if output_err:
        try:
            raise Exception('Git http backend error: {}'.format(
                force_text(output_err).splitlines()[0]
            ))
        except Exception as error:
            report_error(error, request)

    # Handle failure
    if retcode:
        return HttpResponseServerError(output_err)

    headers, content = output.split(b'\r\n\r\n', 1)
    message = message_from_string(headers.decode('utf-8'))

    # Handle status in response
    if 'status' in message:
        return HttpResponse(
            status=int(message['status'].split()[0])
        )

    # Send content
    response = HttpResponse(
        content_type=message['content-type']
    )
    response.write(content)
    return response
