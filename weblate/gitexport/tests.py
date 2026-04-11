# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os.path
import pathlib
import subprocess  # noqa: S404
import tempfile
from base64 import b64encode
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.test.utils import override_settings
from django.urls import reverse

from weblate.auth.models import Permission, Role
from weblate.gitexport.models import get_export_url
from weblate.gitexport.views import (
    authenticate,
    format_backend_error,
    has_missing_requested_revision,
)
from weblate.trans.models import Project
from weblate.trans.tests.test_models import BaseLiveServerTestCase
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import RepoTestMixin, create_test_user

if TYPE_CHECKING:
    from weblate.trans.models import Component


def pkt_line(payload: bytes) -> bytes:
    return f"{len(payload) + 4:04x}".encode("ascii") + payload


class GitExportTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        # We don't want standard Django authentication
        self.client.logout()

    def mark_component_shallow(self) -> None:
        with open(
            os.path.join(self.component.full_path, ".git", "shallow"),
            "a",
            encoding="ascii",
        ):
            pass

    def get_auth_string(self, code):
        encoded = b64encode(f"{self.user.username}:{code}".encode())
        return f"basic {encoded.decode('ascii')}"

    def test_authenticate_invalid(self) -> None:
        request = HttpRequest()
        self.assertFalse(authenticate(request, "foo"))

    def test_authenticate_missing(self) -> None:
        request = HttpRequest()
        self.assertFalse(authenticate(request, "basic "))

    def test_authenticate_basic_invalid(self) -> None:
        request = HttpRequest()
        self.assertFalse(authenticate(request, "basic fdsafds"))

    def test_authenticate_digest(self) -> None:
        request = HttpRequest()
        self.assertFalse(authenticate(request, "digest fdsafds"))

    def test_authenticate_wrong(self) -> None:
        request = HttpRequest()
        self.assertFalse(authenticate(request, self.get_auth_string("invalid")))

    def test_authenticate_basic(self) -> None:
        request = HttpRequest()
        self.assertTrue(
            authenticate(request, self.get_auth_string(self.user.auth_token.key))
        )

    def test_authenticate_inactive(self) -> None:
        self.user.is_active = False
        self.user.save()
        request = HttpRequest()
        self.assertFalse(
            authenticate(request, self.get_auth_string(self.user.auth_token.key))
        )

    def get_git_url(
        self, *, path: str = "info/refs", component: Component | None = None
    ):
        if component is None:
            component = self.component
        kwargs = {"git_request": path, "path": component.get_url_path()}
        return reverse("git-export", kwargs=kwargs)

    def test_git_root(self) -> None:
        response = self.client.get(self.get_git_url().replace("info/refs", ""))
        self.assertEqual(301, response.status_code)

    def test_git_info(self) -> None:
        response = self.client.get(
            self.get_git_url().replace("info/refs", "info/"), follow=True
        )
        self.assertEqual(404, response.status_code)

    def git_receive(self, **kwargs):
        return self.client.get(
            self.get_git_url(),
            {"service": "git-upload-pack"},
            CONTENT_TYPE="application/x-git-upload-pack-advertisement",
            **kwargs,
        )

    def test_redirect_link(self) -> None:
        linked = self.create_link_existing()
        response = self.client.get(
            self.get_git_url(component=linked),
            {"service": "git-upload-pack"},
            CONTENT_TYPE="application/x-git-upload-pack-advertisement",
        )
        self.assertRedirects(
            response,
            "/git/test/test/info/refs?service=git-upload-pack",
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_reject_push(self) -> None:
        self.component.push = "https://user:secret@example.com/upstream.git"
        self.component.save(update_fields=["push"])
        response = self.client.get(self.get_git_url(), {"service": "git-receive-pack"})
        self.assertContains(
            response, "https://example.com/upstream.git", status_code=403
        )
        self.assertNotContains(response, "user:secret@", status_code=403)

    def test_reject_push_post(self) -> None:
        self.component.push = "https://user:secret@example.com/upstream.git"
        self.component.save(update_fields=["push"])
        response = self.client.generic(
            "POST",
            self.get_git_url(path="git-receive-pack"),
            b"",
            CONTENT_TYPE="application/x-git-receive-pack-request",
        )
        self.assertContains(
            response, "https://example.com/upstream.git", status_code=403
        )
        self.assertNotContains(response, "user:secret@", status_code=403)

    def test_reject_push_no_url_leak_without_permission(self) -> None:
        self.component.push = "https://user:secret@example.com/upstream.git"
        self.component.save(update_fields=["push"])
        self.enable_acl()
        response = self.client.get(
            self.get_git_url(),
            {"service": "git-receive-pack"},
            headers={"authorization": self.get_auth_string(self.user.auth_token.key)},
        )
        self.assertEqual(404, response.status_code)
        self.assertNotIn("https://example.com/upstream.git", response.content.decode())
        self.assertNotIn("user:secret@", response.content.decode())

    def test_wrong_auth(self) -> None:
        response = self.git_receive(HTTP_AUTHORIZATION="foo")
        self.assertEqual(401, response.status_code)

    def test_unsupported_service(self) -> None:
        response = self.client.get(self.get_git_url(), {"service": "git-foo-pack"})
        self.assertEqual(403, response.status_code)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(response.content.decode(), "Unsupported Git service.\n")

    def test_git_receive(self) -> None:
        response = self.git_receive()
        self.assertContains(response, "refs/heads/main")

    def test_git_receive_error(self) -> None:
        response = self.git_receive(HTTP_X_WEBLATE_NO_EXPORT="1")
        self.assertEqual(404, response.status_code)

    def enable_acl(self) -> None:
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()

    def add_access_only_user(self) -> None:
        role = Role.objects.create(name="Git export access only")
        role.permissions.add(Permission.objects.get(codename="vcs.access"))
        self.project.defined_groups.get(name="VCS").roles.set([role])
        self.project.add_user(self.user, "VCS")

    def test_git_receive_acl_denied(self) -> None:
        self.enable_acl()
        response = self.git_receive()
        self.assertEqual(401, response.status_code)

    def test_git_receive_acl_auth(self) -> None:
        self.enable_acl()
        self.project.add_user(self.user, "VCS")
        response = self.git_receive(
            HTTP_AUTHORIZATION=self.get_auth_string(self.user.auth_token.key)
        )
        self.assertContains(response, "refs/heads/main")

    def test_git_receive_acl_auth_denied(self) -> None:
        self.enable_acl()
        response = self.git_receive(
            HTTP_AUTHORIZATION=self.get_auth_string(self.user.auth_token.key)
        )
        self.assertEqual(404, response.status_code)

    def test_get_export_url(self) -> None:
        self.assertEqual(
            "http://example.com/git/test/test/", get_export_url(self.component)
        )

    def test_reject_push_without_explicit_push_url(self) -> None:
        self.component.repo = "https://private.example/repo.git"
        self.component.push = ""
        self.component.save(update_fields=["repo", "push"])
        response = self.client.get(self.get_git_url(), {"service": "git-receive-pack"})
        self.assertContains(
            response,
            "Push to the upstream repository instead.",
            status_code=403,
        )
        self.assertNotContains(response, "private.example", status_code=403)

    def test_reject_push_no_url_leak_without_vcs_view(self) -> None:
        self.component.push = "https://user:secret@example.com/upstream.git"
        self.component.save(update_fields=["push"])
        self.enable_acl()
        self.add_access_only_user()
        response = self.client.get(
            self.get_git_url(),
            {"service": "git-receive-pack"},
            headers={"authorization": self.get_auth_string(self.user.auth_token.key)},
        )
        self.assertContains(
            response,
            "Push to the upstream repository instead.",
            status_code=403,
        )
        self.assertNotContains(
            response, "https://example.com/upstream.git", status_code=403
        )
        self.assertNotContains(response, "user:secret@", status_code=403)

    def test_missing_revision_error_message(self) -> None:
        self.component.repo = "https://user:secret@example.com/upstream.git"
        message = format_backend_error(
            self.component,
            "fatal: git upload-pack: not our ref deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            can_view=True,
        )

        self.assertIn("Fetch it from the upstream repository first", message)
        self.assertIn("https://example.com/upstream.git", message)
        self.assertNotIn("user:secret@", message)

    def test_generic_backend_error_is_sanitized(self) -> None:
        self.component.push = "https://user:secret@example.com/upstream.git"
        message = format_backend_error(
            self.component,
            "fatal: unable to access "
            "'https://user:secret@example.com/upstream.git': "
            "Could not resolve host: internal.example.net\n"
            f"{self.component.full_path}/.git/index.lock",
            can_view=True,
        )

        self.assertIn("repository URL", message)
        self.assertIn("Could not resolve host: ...", message)
        self.assertNotIn("user:secret@", message)
        self.assertNotIn(self.component.full_path, message)

    def test_missing_revision_error_message_without_vcs_view(self) -> None:
        self.component.repo = "https://private.example/repo.git"
        message = format_backend_error(
            self.component,
            "fatal: git upload-pack: not our ref deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            can_view=False,
        )

        self.assertIn("Fetch it from the upstream repository first.", message)
        self.assertNotIn("private.example", message)

    def test_detect_missing_requested_revision(self) -> None:
        self.mark_component_shallow()
        body = (
            pkt_line(
                b"want deadbeefdeadbeefdeadbeefdeadbeefdeadbeef multi_ack_detailed\n"
            )
            + b"0000"
        )

        self.assertTrue(has_missing_requested_revision(self.component, body))

    def test_ignore_missing_requested_have(self) -> None:
        self.mark_component_shallow()
        present_revision = self.component.repository.execute(
            ["rev-parse", "HEAD"],
            needs_lock=False,
        ).strip()
        body = (
            pkt_line(f"have {present_revision}\n".encode("ascii"))
            + pkt_line(b"have deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n")
            + b"0000"
        )

        self.assertFalse(has_missing_requested_revision(self.component, body))

    def test_detect_missing_requested_have_without_common_base(self) -> None:
        self.mark_component_shallow()
        present_revision = self.component.repository.execute(
            ["rev-parse", "HEAD"],
            needs_lock=False,
        ).strip()
        body = (
            pkt_line(f"want {present_revision}\n".encode("ascii"))
            + pkt_line(b"have deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n")
            + b"0000"
        )

        self.assertTrue(has_missing_requested_revision(self.component, body))

    def test_skip_missing_revision_precheck_for_non_shallow_checkout(self) -> None:
        body = (
            pkt_line(
                b"want deadbeefdeadbeefdeadbeefdeadbeefdeadbeef multi_ack_detailed\n"
            )
            + b"0000"
        )

        with (
            patch("weblate.gitexport.views.is_shallow_checkout", return_value=False),
            patch.object(self.component.repository, "execute") as execute,
        ):
            self.assertFalse(has_missing_requested_revision(self.component, body))

        execute.assert_not_called()

    def test_missing_revision_precheck_response(self) -> None:
        self.mark_component_shallow()
        self.component.repo = "https://user:secret@example.com/upstream.git"
        self.component.save(update_fields=["repo"])
        body = (
            pkt_line(
                b"want deadbeefdeadbeefdeadbeefdeadbeefdeadbeef multi_ack_detailed\n"
            )
            + b"0000"
        )

        response = self.client.generic(
            "POST",
            self.get_git_url(path="git-upload-pack"),
            body,
            CONTENT_TYPE="application/x-git-upload-pack-request",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/x-git-upload-pack-result",
        )
        self.assertIn(
            b"ERR The requested revision is not available in Weblate's local Git "
            b"checkout. Fetch it from the upstream repository first: "
            b"https://example.com/upstream.git",
            response.content,
        )
        self.assertTrue(response.content.endswith(b"0000"))
        self.assertNotIn(b"user:secret@", response.content)

    def test_no_common_base_precheck_response(self) -> None:
        self.mark_component_shallow()
        self.component.repo = "https://user:secret@example.com/upstream.git"
        self.component.save(update_fields=["repo"])
        present_revision = self.component.repository.execute(
            ["rev-parse", "HEAD"],
            needs_lock=False,
        ).strip()
        body = (
            pkt_line(f"want {present_revision}\n".encode("ascii"))
            + pkt_line(b"have deadbeefdeadbeefdeadbeefdeadbeefdeadbeef\n")
            + b"0000"
        )

        response = self.client.generic(
            "POST",
            self.get_git_url(path="git-upload-pack"),
            body,
            CONTENT_TYPE="application/x-git-upload-pack-request",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/x-git-upload-pack-result",
        )
        self.assertIn(
            b"ERR Weblate's shallow Git checkout does not share enough history "
            b"with this repository to satisfy the fetch.",
            response.content,
        )
        self.assertIn(
            b"Upstream repository: https://example.com/upstream.git", response.content
        )
        self.assertTrue(response.content.endswith(b"0000"))
        self.assertNotIn(b"user:secret@", response.content)

    def test_skip_missing_revision_precheck_in_view_for_non_shallow_checkout(
        self,
    ) -> None:
        with (
            patch("weblate.gitexport.views.is_shallow_checkout", return_value=False),
            patch("weblate.gitexport.views.get_precheck_failure_reason") as precheck,
            patch("weblate.gitexport.views.GitHTTPBackendWrapper") as wrapper_cls,
        ):
            wrapper = wrapper_cls.return_value
            wrapper.get_response.return_value = HttpResponse(status=204)
            response = self.client.generic(
                "POST",
                self.get_git_url(path="git-upload-pack"),
                b"",
                CONTENT_TYPE="application/x-git-upload-pack-request",
            )

        self.assertEqual(response.status_code, 204)
        precheck.assert_not_called()


class GitCloneTest(BaseLiveServerTestCase, RepoTestMixin):
    """Integration tests using git to clone the repo."""

    acl = True

    def create_export_component(self) -> Component:
        return self.create_component()

    def setUp(self) -> None:
        super().setUp()
        self.clone_test_repos()
        self.component = self.create_export_component()
        self.component.project.access_control = Project.ACCESS_PRIVATE
        self.component.project.save()
        self.user = create_test_user()

    def test_clone(self) -> None:
        with tempfile.TemporaryDirectory() as testdir:
            if self.acl:
                self.component.project.add_user(self.user, "VCS")
            url = (
                get_export_url(self.component)
                .replace("http://example.com", self.live_server_url)
                .replace(
                    "http://",
                    f"http://{self.user.username}:{self.user.auth_token.key}@",
                )
            )
            with subprocess.Popen(  # noqa: S603
                ["git", "clone", url],  # noqa: S607
                cwd=testdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
            ) as process:
                output = process.communicate()[0]
                retcode = process.poll()

        check = self.assertEqual if self.acl else self.assertNotEqual
        check(retcode, 0, f"Failed: {output}")


class GitCloneFailTest(GitCloneTest):
    acl = False


class GitCloneShallowTest(GitCloneTest):
    def create_export_component(self) -> Component:
        with override_settings(VCS_CLONE_DEPTH=1):
            return self.create_component()

    def test_clone(self) -> None:
        self.assertTrue(
            os.path.exists(os.path.join(self.component.full_path, ".git", "shallow"))
        )
        super().test_clone()

    def test_fetch_from_unrelated_clone(self) -> None:
        self.component.repo = "https://user:secret@example.com/upstream.git"
        self.component.save(update_fields=["repo"])
        self.component.project.add_user(self.user, "VCS")

        url = (
            get_export_url(self.component)
            .replace("http://example.com", self.live_server_url)
            .replace(
                "http://",
                f"http://{self.user.username}:{self.user.auth_token.key}@",
            )
        )

        with tempfile.TemporaryDirectory() as testdir:
            subprocess.check_call(
                ["git", "init", "existing"],  # noqa: S607
                cwd=testdir,
            )
            subprocess.check_call(
                cwd=os.path.join(testdir, "existing"),
                args=["git", "config", "user.name", "Test"],
            )
            subprocess.check_call(
                cwd=os.path.join(testdir, "existing"),
                args=["git", "config", "user.email", "test@example.com"],
            )
            for name in ("a", "b", "c"):
                pathlib.Path(os.path.join(testdir, "existing", "other.txt")).write_text(
                    f"{name}\n", encoding="utf-8"
                )
                subprocess.check_call(
                    ["git", "add", "other.txt"],  # noqa: S607
                    cwd=os.path.join(testdir, "existing"),
                )
                subprocess.check_call(  # noqa: S603
                    ["git", "commit", "-m", name],  # noqa: S607
                    cwd=os.path.join(testdir, "existing"),
                )
            subprocess.check_call(  # noqa: S603
                ["git", "remote", "add", "weblate", url],  # noqa: S607
                cwd=os.path.join(testdir, "existing"),
            )
            with subprocess.Popen(
                ["git", "fetch", "weblate"],  # noqa: S607
                cwd=os.path.join(testdir, "existing"),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
            ) as process:
                output = process.communicate()[0]
                retcode = process.poll()

        self.assertNotEqual(retcode, 0, output)
        self.assertIn(
            "does not share enough history with this repository to satisfy the fetch",
            output,
        )
        self.assertIn("https://example.com/upstream.git", output)
        self.assertNotIn("user:secret@", output)
