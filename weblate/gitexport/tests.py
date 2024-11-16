# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import subprocess
import tempfile
from base64 import b64encode

from django.http.request import HttpRequest
from django.urls import reverse

from weblate.gitexport.models import get_export_url
from weblate.gitexport.views import authenticate
from weblate.trans.models import Component, Project
from weblate.trans.tests.test_models import BaseLiveServerTestCase
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import RepoTestMixin, create_test_user


class GitExportTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        # We don't want standard Django authentication
        self.client.logout()

    def get_auth_string(self, code):
        encoded = b64encode(f"{self.user.username}:{code}".encode())
        return "basic " + encoded.decode("ascii")

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
        response = self.client.get(self.get_git_url(), {"service": "git-receive-pack"})
        self.assertEqual(403, response.status_code)

    def test_wrong_auth(self) -> None:
        response = self.git_receive(HTTP_AUTHORIZATION="foo")
        self.assertEqual(401, response.status_code)

    def test_git_receive(self) -> None:
        response = self.git_receive()
        self.assertContains(response, "refs/heads/main")

    def test_git_receive_error(self) -> None:
        response = self.git_receive(HTTP_X_WEBLATE_NO_EXPORT="1")
        self.assertEqual(404, response.status_code)

    def enable_acl(self) -> None:
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()

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


class GitCloneTest(BaseLiveServerTestCase, RepoTestMixin):
    """Integration tests using git to clone the repo."""

    acl = True

    def setUp(self) -> None:
        super().setUp()
        self.clone_test_repos()
        self.component = self.create_component()
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
            process = subprocess.Popen(
                ["git", "clone", url],
                cwd=testdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
            )
            output = process.communicate()[0]
            retcode = process.poll()

        check = self.assertEqual if self.acl else self.assertNotEqual
        check(retcode, 0, f"Failed: {output}")


class GitCloneFailTest(GitCloneTest):
    acl = False
