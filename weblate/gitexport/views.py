# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os.path
import subprocess
from base64 import b64decode
from email import message_from_string
from functools import partial
from selectors import EVENT_READ, DefaultSelector

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404, StreamingHttpResponse
from django.http.response import HttpResponse, HttpResponseServerError
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from weblate.auth.models import User
from weblate.gitexport.models import SUPPORTED_VCS
from weblate.gitexport.utils import find_git_http_backend
from weblate.trans.models import Component
from weblate.utils.errors import report_error
from weblate.utils.views import parse_path


def response_authenticate():
    """Return 401 response with authenticate header."""
    response = HttpResponse(status=401)
    response["WWW-Authenticate"] = 'Basic realm="Weblate Git access"'
    return response


def authenticate(request, auth):
    """Perform authentication with HTTP Basic auth."""
    try:
        method, data = auth.split(None, 1)
    except (ValueError, TypeError):
        return False
    if method.lower() == "basic":
        try:
            username, code = b64decode(data).decode("iso-8859-1").split(":", 1)
        except (ValueError, TypeError):
            return False
        try:
            user = User.objects.get(username=username, auth_token__key=code)
        except User.DoesNotExist:
            return False

        if not user.is_active:
            return False

        request.user = user
        return True
    return False


@never_cache
@csrf_exempt
def git_export(request, path, git_request):
    """
    Git HTTP server view.

    Wrapper around git-http-backend to provide Git repositories export over HTTP.
    Performs permission checks and hands over execution to the wrapper.
    """
    # Reject non pull access early
    if request.GET.get("service", "") not in ("", "git-upload-pack"):
        raise PermissionDenied("Only pull is supported")

    # HTTP authentication
    auth = request.headers.get("authorization", b"")

    if auth and not authenticate(request, auth):
        return response_authenticate()

    try:
        obj = parse_path(request, path, (Component,))
    except Http404:
        if not request.user.is_authenticated:
            return response_authenticate()
        raise
    # Strip possible double path separators
    git_request = git_request.lstrip("/\\")

    # Permissions
    if not request.user.has_perm("vcs.access", obj):
        if not request.user.is_authenticated:
            return response_authenticate()
        raise PermissionDenied("No VCS permissions")
    if obj.vcs not in SUPPORTED_VCS:
        raise Http404("Not a git repository")
    if obj.is_repo_link:
        return redirect(
            "{}?{}".format(
                reverse(
                    "git-export",
                    kwargs={
                        "path": obj.linked_component.get_url_path(),
                        "git_request": git_request,
                    },
                ),
                request.META["QUERY_STRING"],
            ),
            permanent=True,
        )

    return run_git_http(request, obj, git_request)


class GitHTTPBackendWrapper:
    def __init__(self, obj, request, git_request: str):
        self.path = os.path.join(obj.full_path, git_request)
        self.obj = obj
        self.request = request
        self.selector = DefaultSelector()
        self._headers = None
        self._stderr = []
        self._stdout = []

        # Find Git HTTP backend
        git_http_backend = find_git_http_backend()
        if git_http_backend is None:
            raise SuspiciousOperation("git-http-backend not found")

        # Invoke Git HTTP backend
        self.process = subprocess.Popen(
            [git_http_backend],
            env=self.get_env(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            close_fds=True,
            bufsize=0,
        )

    def get_env(self):
        result = {
            "REQUEST_METHOD": self.request.method,
            "PATH_TRANSLATED": self.path,
            "GIT_HTTP_EXPORT_ALL": "1",
            "CONTENT_TYPE": self.request.headers.get("content-type", ""),
            "QUERY_STRING": self.request.META.get("QUERY_STRING", ""),
            "HTTP_CONTENT_ENCODING": self.request.headers.get("content-encoding", ""),
        }
        # Fault injection in tests
        if "X_WEBLATE_NO_EXPORT" in self.request.headers:
            del result["GIT_HTTP_EXPORT_ALL"]
        return result

    def send_body(self):
        self.process.stdin.write(self.request.body)
        self.process.stdin.close()

    def fetch_headers(self):
        """Fetch initial chunk of response to parse headers."""
        while True:
            for key, _mask in self.selector.select(timeout=1):
                if key.data:
                    self._stdout.append(self.process.stdout.read(1024))
                    headers = b"".join(self._stdout)
                    if b"\r\n\r\n" in headers:
                        self._headers, body = headers.split(b"\r\n\r\n", 1)
                        self._stdout = [body]
                else:
                    self._stderr.append(self.process.stderr.read())
            if self.process.poll() is not None or self._headers is not None:
                break

    def stream(self):
        yield from self._stdout
        yield from iter(partial(self.process.stdout.read, 1024), b"")

    def get_response(self):
        # Iniciate select()
        self.selector.register(self.process.stdout, EVENT_READ, True)
        self.selector.register(self.process.stderr, EVENT_READ, False)

        # Send request body
        self.send_body()

        # Read initial chunk of response to parse headers
        # This assumes that git-http-backend will fail here if it will fail
        self.fetch_headers()

        self.selector.unregister(self.process.stdout)
        self.selector.unregister(self.process.stderr)
        self.selector.close()

        retcode = self.process.poll()

        output_err = b"".join(self._stderr).decode()

        # Log error
        if output_err:
            report_error(
                cause="Git backend failure",
                extra_log=output_err,
                project=self.obj.project,
                level="error",
                message=True,
            )

        # Handle failure
        if retcode:
            return HttpResponseServerError(output_err)

        message = message_from_string(self._headers.decode())

        # Handle status in response
        if "status" in message:
            return HttpResponse(status=int(message["status"].split()[0]))

        # Send streaming content as reponse
        return StreamingHttpResponse(
            streaming_content=self.stream(), content_type=message["content-type"]
        )


def run_git_http(request, obj, git_request):
    """Git HTTP backend execution wrapper."""
    # Invoke Git HTTP backend
    wrapper = GitHTTPBackendWrapper(obj, request, git_request)
    return wrapper.get_response()
