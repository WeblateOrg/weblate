# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os.path
import subprocess
from base64 import b64decode
from contextlib import suppress
from email import message_from_string
from functools import partial
from selectors import EVENT_READ, DefaultSelector
from typing import TYPE_CHECKING, BinaryIO, cast

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404, StreamingHttpResponse
from django.http.response import HttpResponse, HttpResponseBase, HttpResponseServerError
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from weblate.auth.models import AuthenticatedHttpRequest, User
from weblate.gitexport.utils import find_git_http_backend
from weblate.trans.models import Component
from weblate.utils.errors import report_error
from weblate.utils.views import parse_path
from weblate.vcs.models import VCS_REGISTRY

if TYPE_CHECKING:
    from collections.abc import Iterator


def response_authenticate():
    """Return 401 response with authenticate header."""
    response = HttpResponse(status=401)
    response["WWW-Authenticate"] = 'Basic realm="Weblate Git access"'
    return response


def authenticate(request: AuthenticatedHttpRequest, auth: str) -> bool:
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
def git_export(
    request: AuthenticatedHttpRequest, path: list[str], git_request: str
) -> HttpResponseBase:
    """
    Git HTTP server view.

    Wrapper around git-http-backend to provide Git repositories export over HTTP.
    Performs permission checks and hands over execution to the wrapper.
    """
    # Reject non pull access early
    if request.GET.get("service", "") not in {"", "git-upload-pack"}:
        msg = "Only pull is supported"
        raise PermissionDenied(msg)

    # HTTP authentication
    auth = request.headers.get("authorization", "")

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
        msg = "No VCS permissions"
        raise PermissionDenied(msg)
    if obj.vcs not in VCS_REGISTRY.git_based:
        msg = "Not a git repository"
        raise Http404(msg)
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

    # Invoke Git HTTP backend
    wrapper = GitHTTPBackendWrapper(obj, request, git_request)
    return wrapper.get_response()


class GitStreamingHttpResponse(StreamingHttpResponse):
    def __init__(self, streaming_content, *args, **kwargs) -> None:
        super().__init__(streaming_content.stream(), *args, **kwargs)
        self.wrapper = streaming_content

    def close(self) -> None:
        if self.wrapper.process.poll() is None:
            self.wrapper.process.kill()
        self.wrapper.process.wait()
        super().close()


class GitHTTPBackendWrapper:
    def __init__(
        self, obj, request: AuthenticatedHttpRequest, git_request: str
    ) -> None:
        self.path = os.path.join(obj.full_path, git_request)
        self.obj = obj
        self.request = request
        self.selector = DefaultSelector()
        self._headers: bytes = b""
        self._stderr: list[bytes] = []
        self._stdout: list[bytes] = []

        # Find Git HTTP backend
        git_http_backend = find_git_http_backend()
        if git_http_backend is None:
            msg = "git-http-backend not found"
            raise SuspiciousOperation(msg)

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

    def get_env(self) -> dict[str, str]:
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

    def send_body(self) -> None:
        # Fetch request body (it could be streamed)
        body = self.request.body

        with suppress(BrokenPipeError):
            # Ignore broken pipe as that can happen when process failed with an error
            self.process.stdin.write(body)  # type: ignore[union-attr]

        self.process.stdin.close()  # type: ignore[union-attr]

    def fetch_headers(self) -> None:
        """Fetch initial chunk of response to parse headers."""
        while True:
            for key, _mask in self.selector.select(timeout=1):
                if key.data:
                    self._stdout.append(
                        self.process.stdout.read(1024)  # type: ignore[union-attr]
                    )
                    headers = b"".join(self._stdout)
                    if b"\r\n\r\n" in headers:
                        self._headers, body = headers.split(b"\r\n\r\n", 1)
                        self._stdout = [body]
                else:
                    self._stderr.append(
                        self.process.stderr.read()  # type: ignore[union-attr]
                    )
            if self.process.poll() is not None or self._headers is not None:
                break

    def stream(self) -> Iterator[bytes]:
        yield from self._stdout
        yield from iter(
            partial(self.process.stdout.read, 1024),  # type: ignore[union-attr]
            b"",
        )

    def get_response(self) -> HttpResponseBase:
        # Iniciate select()
        stdout = cast("BinaryIO", self.process.stdout)
        stderr = cast("BinaryIO", self.process.stderr)
        self.selector.register(stdout, EVENT_READ, True)
        self.selector.register(stderr, EVENT_READ, False)

        # Send request body
        self.send_body()

        # Read initial chunk of response to parse headers
        # This assumes that git-http-backend will fail here if it will fail
        self.fetch_headers()

        self.selector.unregister(stdout)
        self.selector.unregister(stderr)
        self.selector.close()

        retcode = self.process.poll()

        output_err = b"".join(self._stderr).decode()

        # Log error
        if output_err:
            report_error(
                "Git backend failure",
                extra_log=output_err,
                project=self.obj.project,
                level="error",
                message=True,
            )

        # Handle failure
        if retcode is not None and retcode != 0:
            return HttpResponseServerError(output_err)

        message = message_from_string(self._headers.decode())

        # Handle status in response
        if "status" in message:
            self.process.wait()
            return HttpResponse(status=int(message["status"].split()[0]))

        # Send streaming content as response
        return GitStreamingHttpResponse(
            streaming_content=self, content_type=message["content-type"]
        )
