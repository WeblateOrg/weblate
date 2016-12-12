# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from base64 import b64decode
from email import message_from_string
import os.path
import subprocess

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http.response import HttpResponseServerError, HttpResponse
from django.shortcuts import redirect
from django.utils.six import text_type
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache

from weblate.trans.views.helper import get_subproject


def response_authenticate():
    """
    Returns 401 response with authenticate header.
    """
    response = HttpResponse(status=401)
    response['WWW-Authenticate'] = 'Basic realm="Git"'
    return response


def authenticate(request, auth):
    """
    Performs authentication with HTTP Basic auth
    """
    if not isinstance(auth, text_type):
        auth = auth.decode('iso-8859-1')
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
def git_export(request, project, subproject, path):
    """
    Wrapper around git-http-backend to provide Git
    repositories export over HTTP.
    """
    # Probably browser access
    if path == '':
        return redirect(
            'subproject',
            project=project,
            subproject=subproject,
            permanent=False
        )

    # HTTP authentication
    auth = request.META.get('HTTP_AUTHORIZATION', b'')

    if auth:
        if not authenticate(request, auth):
            return response_authenticate()

    # Permissions
    try:
        obj = get_subproject(request, project, subproject)
    except PermissionDenied:
        if not request.user.is_authenticated():
            return response_authenticate()
        raise

    # Invoke Git HTTP backend
    process = subprocess.Popen(
        ['/usr/lib/git-core/git-http-backend'],
        env={
            'REQUEST_METHOD': request.method,
            'PATH_TRANSLATED': os.path.join(obj.get_path(), path),
            'GIT_HTTP_EXPORT_ALL': '1',
            'CONTENT_TYPE': request.META.get('CONTENT_TYPE', ''),
            'QUERY_STRING': request.META.get('QUERY_STRING', ''),
            'HTTP_CONTENT_ENCODING': request.META.get(
                'HTTP_CONTENT_ENCODING', ''
            ),
        },
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    output, output_err = process.communicate(request.body)
    retcode = process.poll()

    # Log error
    if output_err:
        try:
            obj.log_error('git: {0}'.format(output_err.decode('utf-8')))
        except UnicodeDecodeError:
            obj.log_error('git: {0}'.format(repr(output_err)))

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
