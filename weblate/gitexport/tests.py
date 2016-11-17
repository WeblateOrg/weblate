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

from base64 import b64encode

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.http.request import HttpRequest

from weblate.gitexport.views import authenticate
from weblate.trans.tests.test_views import ViewTestCase


class GitExportTest(ViewTestCase):
    def test_authenticate(self):
        user = User.objects.create_user('somebody', 'foo@example.net', 'x')
        request = HttpRequest()
        self.assertFalse(authenticate(request, 'foo'))
        self.assertFalse(authenticate(request, 'basic '))
        self.assertFalse(authenticate(request, 'basic fdsafds'))
        self.assertFalse(authenticate(
            request,
            'basic ' + b64encode('somebody:invalid')
        ))
        self.assertTrue(authenticate(
            request,
            'basic ' + b64encode('somebody:' + user.auth_token.key)
        ))

    def get_git_url(self, path):
        kwargs = {'path': path}
        kwargs.update(self.kw_subproject)
        return reverse('git-export', kwargs=kwargs)

    def test_git_root(self):
        response = self.client.get(self.get_git_url(''))
        self.assertEquals(404, response.status_code)

    def test_git_receive(self):
        response = self.client.get(
            self.get_git_url('info/refs'),
            QUERY_STRING='?service=git-receive-pack',
            CONTENT_TYPE='application/x-git-upload-pack-advertisement',
        )
        self.assertContains(response, 'refs/heads/master')
