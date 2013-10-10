# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

from trans.tests.views import ViewTestCase
import trans.admin_views
from django.test import TestCase
from django.core.urlresolvers import reverse
from trans.tests.util import get_test_file
import tempfile
import shutil
import os

TEST_HOSTS = get_test_file('known_hosts')


class AdminTest(ViewTestCase):
    '''
    Tests for customized admin interface.
    '''
    def setUp(self):
        super(AdminTest, self).setUp()
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()

    def test_index(self):
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'SSH')

    def test_ssh(self):
        response = self.client.get(reverse('admin-ssh'))
        self.assertContains(response, 'SSH keys')

    def test_ssh_generate(self):
        tempdir = tempfile.mkdtemp()
        rsafile = os.path.join(tempdir, 'id_rsa.pub')
        try:
            backup = trans.admin_views.RSA_KEY_FILE
            trans.admin_views.RSA_KEY_FILE = rsafile

            response = self.client.get(reverse('admin-ssh'))
            self.assertContains(response, 'Generate SSH key')

            response = self.client.post(
                reverse('admin-ssh'),
                {'action': 'generate'}
            )
            self.assertContains(response, 'Created new SSH key')

        finally:
            trans.admin_views.RSA_KEY_FILE = backup
            shutil.rmtree(tempdir)

    def test_performace(self):
        response = self.client.get(reverse('admin-performance'))
        self.assertContains(response, 'Django caching')

    def test_report(self):
        response = self.client.get(reverse('admin-report'))
        self.assertContains(response, 'On branch master')

    def test_create_project(self):
        response = self.client.get(reverse('admin:trans_project_add'))
        self.assertContains(response, 'Required fields are marked as bold')

    def test_create_subproject(self):
        response = self.client.get(reverse('admin:trans_subproject_add'))
        self.assertContains(
            response, 'Importing a new translation can take some time'
        )


class SSHKeysTest(TestCase):
    def test_parse(self):
        try:
            backup = trans.admin_views.KNOWN_HOSTS_FILE
            trans.admin_views.KNOWN_HOSTS_FILE = TEST_HOSTS
            hosts = trans.admin_views.get_host_keys()
            self.assertEqual(len(hosts), 50)
        finally:
            trans.admin_views.KNOWN_HOSTS_FILE = backup
