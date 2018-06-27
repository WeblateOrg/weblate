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

import os

from django.conf import settings
from django.urls import reverse

from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.util import add_configuration_error
from weblate.trans.tests.utils import get_test_file
from weblate.utils.data import check_data_writable
from weblate.utils.unittest import tempdir_setting


class AdminTest(FixtureTestCase):
    """Test for customized admin interface."""
    def setUp(self):
        super(AdminTest, self).setUp()
        self.user.is_superuser = True
        self.user.save()

    def test_index(self):
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'SSH')

    def test_ssh(self):
        response = self.client.get(reverse('admin:ssh'))
        self.assertContains(response, 'SSH keys')

    @tempdir_setting('DATA_DIR')
    def test_ssh_generate(self):
        self.assertEqual(check_data_writable(), [])
        response = self.client.get(reverse('admin:ssh'))
        self.assertContains(response, 'Generate SSH key')

        response = self.client.post(
            reverse('admin:ssh'),
            {'action': 'generate'}
        )
        self.assertContains(response, 'Created new SSH key')

    @tempdir_setting('DATA_DIR')
    def test_ssh_add(self):
        self.assertEqual(check_data_writable(), [])
        try:
            oldpath = os.environ['PATH']
            os.environ['PATH'] = ':'.join(
                (get_test_file(''), os.environ['PATH'])
            )
            # Verify there is button for adding
            response = self.client.get(reverse('admin:ssh'))
            self.assertContains(response, 'Add host key')

            # Add the key
            response = self.client.post(
                reverse('admin:ssh'),
                {'action': 'add-host', 'host': 'github.com'}
            )
            self.assertContains(response, 'Added host key for github.com')
        finally:
            os.environ['PATH'] = oldpath

        # Check the file contains it
        hostsfile = os.path.join(settings.DATA_DIR, 'ssh', 'known_hosts')
        with open(hostsfile) as handle:
            self.assertIn('github.com', handle.read())

    def test_performace(self):
        response = self.client.get(reverse('admin:performance'))
        self.assertContains(response, 'Django caching')

    def test_error(self):
        add_configuration_error('Test error', 'FOOOOOOOOOOOOOO')
        response = self.client.get(reverse('admin:performance'))
        self.assertContains(response, 'FOOOOOOOOOOOOOO')

    def test_report(self):
        response = self.client.get(reverse('admin:report'))
        self.assertContains(response, 'On branch master')

    def test_create_project(self):
        response = self.client.get(reverse('admin:trans_project_add'))
        self.assertContains(response, 'Required fields are marked in bold')

    def test_create_component(self):
        response = self.client.get(reverse('admin:trans_component_add'))
        self.assertContains(response, 'Import speed documentation')

    def test_component(self):
        """Test for custom component actions."""
        self.assert_custom_admin(
            reverse('admin:trans_component_changelist')
        )

    def test_project(self):
        """Test for custom project actions."""
        self.assert_custom_admin(
            reverse('admin:trans_project_changelist')
        )

    def assert_custom_admin(self, url):
        """Test for (sub)project custom admin."""
        response = self.client.get(url)
        self.assertContains(
            response, 'Update VCS repository'
        )
        for action in 'force_commit', 'update_checks', 'update_from_git':
            response = self.client.post(
                url,
                {
                    '_selected_action': '1',
                    'action': action,
                }
            )
            self.assertRedirects(response, url)
