#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

import subprocess
import tempfile
from base64 import b64encode

from django.http.request import HttpRequest
from django.urls import reverse

from weblate.gitexport.models import get_export_url
from weblate.gitexport.views import authenticate
from weblate.trans.models import Project
from weblate.trans.tests.test_models import BaseLiveServerTestCase
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import RepoTestMixin, create_test_user
from weblate.utils.files import remove_tree


class GitExportTest(ViewTestCase):
    def setUp(self):
        super().setUp()
        # We don't want standard Django authentication
        self.client.logout()

    def get_auth_string(self, code):
        encoded = b64encode(f"{self.user.username}:{code}".encode())
        return "basic " + encoded.decode("ascii")

    def test_authenticate_invalid(self):
        request = HttpRequest()
        self.assertFalse(authenticate(request, "foo"))

    def test_authenticate_missing(self):
        request = HttpRequest()
        self.assertFalse(authenticate(request, "basic "))

    def test_authenticate_basic_invalid(self):
        request = HttpRequest()
        self.assertFalse(authenticate(request, "basic fdsafds"))

    def test_authenticate_digest(self):
        request = HttpRequest()
        self.assertFalse(authenticate(request, "digest fdsafds"))

    def test_authenticate_wrong(self):
        request = HttpRequest()
        self.assertFalse(authenticate(request, self.get_auth_string("invalid")))

    def test_authenticate_basic(self):
        request = HttpRequest()
        self.assertTrue(
            authenticate(request, self.get_auth_string(self.user.auth_token.key))
        )

    def test_authenticate_inactive(self):
        self.user.is_active = False
        self.user.save()
        request = HttpRequest()
        self.assertFalse(
            authenticate(request, self.get_auth_string(self.user.auth_token.key))
        )

    def get_git_url(self, path, component=None):
        kwargs = {"path": ""}
        if component is None:
            component = self.kw_component
        kwargs.update(component)
        return reverse("git-export", kwargs=kwargs) + path

    def test_git_root(self):
        response = self.client.get(self.get_git_url(""))
        self.assertEqual(302, response.status_code)

    def test_git_info(self):
        response = self.client.get(self.get_git_url("info"), follow=True)
        self.assertEqual(404, response.status_code)

    def git_receive(self, **kwargs):
        return self.client.get(
            self.get_git_url("info/refs"),
            QUERY_STRING="?service=git-upload-pack",
            CONTENT_TYPE="application/x-git-upload-pack-advertisement",
            **kwargs,
        )

    def test_redirect_link(self):
        linked = self.create_link_existing()
        response = self.client.get(
            self.get_git_url("info/refs", component=linked.get_reverse_url_kwargs()),
            QUERY_STRING="?service=git-upload-pack",
            CONTENT_TYPE="application/x-git-upload-pack-advertisement",
        )
        self.assertRedirects(
            response,
            "/git/test/test/info/refs??service=git-upload-pack",
            status_code=301,
        )

    def test_reject_push(self):
        response = self.client.get(
            self.get_git_url("info/refs"), {"service": "git-receive-pack"}
        )
        self.assertEqual(403, response.status_code)

    def test_wrong_auth(self):
        response = self.git_receive(HTTP_AUTHORIZATION="foo")
        self.assertEqual(401, response.status_code)

    def test_git_receive(self):
        response = self.git_receive()
        self.assertContains(response, "refs/heads/main")

    def enable_acl(self):
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()

    def test_git_receive_acl_denied(self):
        self.enable_acl()
        response = self.git_receive()
        self.assertEqual(401, response.status_code)

    def test_git_receive_acl_auth(self):
        self.enable_acl()
        self.project.add_user(self.user, "@VCS")
        response = self.git_receive(
            HTTP_AUTHORIZATION=self.get_auth_string(self.user.auth_token.key)
        )
        self.assertContains(response, "refs/heads/main")

    def test_git_receive_acl_auth_denied(self):
        self.enable_acl()
        response = self.git_receive(
            HTTP_AUTHORIZATION=self.get_auth_string(self.user.auth_token.key)
        )
        self.assertEqual(404, response.status_code)

    def test_get_export_url(self):
        self.assertEqual(
            "http://example.com/git/test/test/", get_export_url(self.component)
        )


class GitCloneTest(BaseLiveServerTestCase, RepoTestMixin):
    """Integration tests using git to clone the repo."""

    acl = True

    def setUp(self):
        super().setUp()
        self.clone_test_repos()
        self.component = self.create_component()
        self.component.project.access_control = Project.ACCESS_PRIVATE
        self.component.project.save()
        self.user = create_test_user()

    def test_clone(self):
        testdir = tempfile.mkdtemp()
        if self.acl:
            self.component.project.add_user(self.user, "@VCS")
        try:
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
            )
            output = process.communicate()[0]
            retcode = process.poll()
        finally:
            remove_tree(testdir)

        check = self.assertEqual if self.acl else self.assertNotEqual
        check(retcode, 0, f"Failed: {output}")


class GitCloneFailTest(GitCloneTest):
    acl = False
