# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os.path
import re
import subprocess  # noqa: S404
from base64 import b64decode
from contextlib import suppress
from email import message_from_string
from functools import partial
from selectors import EVENT_READ, DefaultSelector

# pylint: disable-next=unused-import
from typing import TYPE_CHECKING, BinaryIO, cast

from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404, StreamingHttpResponse
from django.http.response import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from weblate.auth.models import User
from weblate.gitexport.utils import find_git_http_backend
from weblate.trans.models import Component
from weblate.trans.util import cleanup_repo_url, sanitize_backend_error_message
from weblate.utils.errors import report_error
from weblate.utils.views import parse_path
from weblate.vcs.base import RepositoryError
from weblate.vcs.models import VCS_REGISTRY

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django.http import HttpRequest
    from django.http.response import HttpResponseBase

    from weblate.auth.models import AuthenticatedHttpRequest

MISSING_REVISION_PATTERNS = (
    re.compile(r"\bnot our ref\b", re.IGNORECASE),
    re.compile(r"\bwant [0-9a-f]{7,64} not valid\b", re.IGNORECASE),
)
WANT_REVISION_LINE_RE = re.compile(
    rb"^want (?P<revision>[0-9a-f]{40,64})(?:[\x00\s]|$)"
)
MAX_PRECHECK_PKT_LINES = 32
MAX_PRECHECK_REVISIONS = 32
PRECHECK_MISSING_WANT = "missing_want"


def response_authenticate():
    """Return 401 response with authenticate header."""
    response = HttpResponse(status=401)
    response["WWW-Authenticate"] = 'Basic realm="Weblate Git access"'
    return response


def response_text(message: str, *, status: int) -> HttpResponse:
    """Return plain text response for Git clients."""
    return HttpResponse(
        f"{message}\n",
        status=status,
        content_type="text/plain; charset=utf-8",
    )


def response_packet_error(message: str, *, service: str) -> HttpResponse:
    """Return protocol-level Git error packet for smart HTTP clients."""
    payload = f"ERR {message}".encode()
    packet = f"{len(payload) + 4:04x}".encode("ascii") + payload + b"0000"
    return HttpResponse(
        packet,
        content_type=f"application/x-{service}-result",
    )


def get_upstream_location(
    component: Component, *, can_view: bool, use_push: bool = False
) -> str | None:
    """Return sanitized upstream location for user-facing errors."""
    if not can_view:
        return None

    location = component.push if use_push else component.repo
    if not location:
        return None

    return cleanup_repo_url(location)


def get_push_error_message(component: Component, *, can_view: bool) -> str:
    """Return guidance for rejected push attempts."""
    location = get_upstream_location(component, can_view=can_view, use_push=True)
    if location is None:
        return gettext(
            "Push is not supported over the Weblate Git exporter. "
            "Push to the upstream repository instead."
        )

    return gettext(
        "Push is not supported over the Weblate Git exporter. "
        "Push to the upstream repository instead: {location}"
    ).format(location=location)


def get_missing_revision_message(component: Component, *, can_view: bool) -> str:
    """Return guidance for missing revisions in local checkout."""
    location = get_upstream_location(component, can_view=can_view)
    if location is None:
        return gettext(
            "The requested revision is not available in Weblate's local Git "
            "checkout. Fetch it from the upstream repository first."
        )

    return gettext(
        "The requested revision is not available in Weblate's local Git "
        "checkout. Fetch it from the upstream repository first: {location}"
    ).format(location=location)


def format_backend_error(
    component: Component, output_err: str, *, can_view: bool
) -> str:
    """Format backend failure for user-facing response."""
    if any(pattern.search(output_err) for pattern in MISSING_REVISION_PATTERNS):
        return get_missing_revision_message(component, can_view=can_view)

    sanitized = sanitize_backend_error_message(
        output_err,
        repo_urls=(component.repo, component.push),
        extra_paths=(component.full_path,),
    )
    if sanitized:
        return sanitized

    return gettext("Git export failed.")


def iter_pkt_lines(body: bytes) -> Iterator[bytes]:
    """Yield pkt-line payloads from the raw Git request body."""
    pos = 0
    body_length = len(body)

    while pos + 4 <= body_length:
        try:
            packet_length = int(body[pos : pos + 4], 16)
        except ValueError:
            return

        pos += 4

        if packet_length <= 4:
            continue

        payload_length = packet_length - 4
        if pos + payload_length > body_length:
            return

        yield body[pos : pos + payload_length]
        pos += payload_length


def get_wanted_revisions(body: bytes) -> list[str] | None:
    """Extract wanted revisions from upload-pack requests."""
    wanted_revisions: list[str] = []
    seen: set[str] = set()
    saw_want = False
    processed_lines = 0

    for line in iter_pkt_lines(body):
        processed_lines += 1
        if processed_lines > MAX_PRECHECK_PKT_LINES:
            return None

        match = WANT_REVISION_LINE_RE.match(line)
        if match is None:
            # Only inspect the initial want block and leave the rest of the
            # negotiation to git-upload-pack.
            if saw_want:
                break
            continue

        saw_want = True
        revision = match.group("revision").decode("ascii")
        if revision in seen:
            continue

        seen.add(revision)
        wanted_revisions.append(revision)

        if len(seen) > MAX_PRECHECK_REVISIONS:
            return None

    return wanted_revisions


def is_shallow_checkout(component: Component) -> bool:
    """Check whether component checkout uses Git shallow clone metadata."""
    has_git_file = getattr(component.repository, "has_git_file", None)
    if callable(has_git_file):
        return bool(has_git_file("shallow"))
    return os.path.exists(os.path.join(component.full_path, ".git", "shallow"))


def get_precheck_failure_reason(component: Component, body: bytes) -> str | None:
    """Return shallow upload-pack precheck failure reason, if any."""
    if not is_shallow_checkout(component):
        return None

    execute = getattr(component.repository, "execute", None)
    if not callable(execute):
        return None

    # Missing wanted revisions are deterministic. In contrast, the absence of
    # "have" lines does not prove the client cannot clone from a shallow export
    # because Git may still handle that negotiation successfully.
    wanted_revisions = get_wanted_revisions(body)
    if wanted_revisions is None:
        return None
    if not wanted_revisions:
        return None

    try:
        output = execute(
            ["cat-file", "--batch-check"],
            needs_lock=False,
            stdin="".join(f"{revision}\n" for revision in wanted_revisions),
        )
    except RepositoryError:
        return None

    missing_revisions = {
        revision
        for revision, line in zip(wanted_revisions, output.splitlines(), strict=False)
        if line.endswith(" missing")
    }
    if any(revision in missing_revisions for revision in wanted_revisions):
        return PRECHECK_MISSING_WANT

    return None


def has_missing_requested_revision(component: Component, body: bytes) -> bool:
    """Check whether upload-pack negotiation will fail on a shallow checkout."""
    return get_precheck_failure_reason(component, body) is not None


def authenticate(request: HttpRequest, auth: str) -> bool:
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
@login_not_required
def git_export(
    request: AuthenticatedHttpRequest, path: list[str], git_request: str
) -> HttpResponseBase:
    """
    Git HTTP server view.

    Wrapper around git-http-backend to provide Git repositories export over HTTP.
    Performs permission checks and hands over execution to the wrapper.
    """
    service = request.GET.get("service", "")

    # Reject unsupported services early
    if service not in {"", "git-upload-pack", "git-receive-pack"}:
        return response_text(gettext("Unsupported Git service."), status=403)

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
        url = reverse(
            "git-export",
            kwargs={
                "path": cast("Component", obj.linked_component).get_url_path(),
                "git_request": git_request,
            },
        )
        return redirect(
            f"{url}?{request.META['QUERY_STRING']}",
            permanent=True,
        )

    can_view = bool(request.user.has_perm("vcs.view", obj))
    is_shallow = is_shallow_checkout(obj)

    if service == "git-receive-pack" or git_request == "git-receive-pack":
        return response_text(get_push_error_message(obj, can_view=can_view), status=403)

    if request.method == "POST" and git_request == "git-upload-pack" and is_shallow:
        precheck_reason = get_precheck_failure_reason(obj, request.body)
        if precheck_reason == PRECHECK_MISSING_WANT:
            return response_packet_error(
                get_missing_revision_message(obj, can_view=can_view),
                service="git-upload-pack",
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
        self.wrapper.wait()
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
        # pylint: disable-next=consider-using-with
        self.process = subprocess.Popen(  # noqa: S603
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

        output_err = b"".join(self._stderr).decode(errors="replace")

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
            return response_text(
                format_backend_error(
                    self.obj,
                    output_err,
                    can_view=bool(self.request.user.has_perm("vcs.view", self.obj)),
                ),
                status=500,
            )

        message = message_from_string(self._headers.decode())

        # Handle status in response
        if "status" in message:
            self.wait()
            return HttpResponse(status=int(message["status"].split()[0]))

        # Send streaming content as response
        return GitStreamingHttpResponse(
            streaming_content=self, content_type=message["content-type"]
        )

    def wait(self) -> None:
        self.process.wait()
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.process.stderr is not None:
            self.process.stderr.close()
