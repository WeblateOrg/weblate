# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

import json
import os
from unittest import skipIf

import httpretty
import six
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.trans.util import add_configuration_error, delete_configuration_error
from weblate.utils.checks import check_data_writable
from weblate.utils.unittest import tempdir_setting
from weblate.wladmin.models import BackupService, ConfigurationError, SupportStatus
from weblate.wladmin.tasks import configuration_health_check


class AdminTest(ViewTestCase):
    """Test for customized admin interface."""

    def setUp(self):
        super(AdminTest, self).setUp()
        self.user.is_superuser = True
        self.user.save()

    def test_index(self):
        response = self.client.get(reverse('admin:index'))
        self.assertContains(response, 'SSH')

    def test_manage_index(self):
        response = self.client.get(reverse('manage'))
        self.assertContains(response, 'SSH')

    def test_ssh(self):
        response = self.client.get(reverse('manage-ssh'))
        self.assertContains(response, 'SSH keys')

    @tempdir_setting('DATA_DIR')
    def test_ssh_generate(self):
        self.assertEqual(check_data_writable(), [])
        response = self.client.get(reverse('manage-ssh'))
        self.assertContains(response, 'Generate SSH key')

        response = self.client.post(reverse('manage-ssh'), {'action': 'generate'})
        self.assertContains(response, 'Created new SSH key')
        response = self.client.get(reverse('manage-ssh-key'))
        self.assertContains(response, 'PRIVATE KEY')

    @tempdir_setting('DATA_DIR')
    def test_ssh_add(self):
        self.assertEqual(check_data_writable(), [])
        try:
            oldpath = os.environ['PATH']
            os.environ['PATH'] = ':'.join((get_test_file(''), os.environ['PATH']))
            # Verify there is button for adding
            response = self.client.get(reverse('manage-ssh'))
            self.assertContains(response, 'Add host key')

            # Add the key
            response = self.client.post(
                reverse('manage-ssh'), {'action': 'add-host', 'host': 'github.com'}
            )
            self.assertContains(response, 'Added host key for github.com')
        finally:
            os.environ['PATH'] = oldpath

        # Check the file contains it
        hostsfile = os.path.join(settings.DATA_DIR, 'ssh', 'known_hosts')
        with open(hostsfile) as handle:
            self.assertIn('github.com', handle.read())

    @tempdir_setting("BACKUP_DIR")
    @skipIf(six.PY2, 'borgbackup does not support Python 2')
    def test_backup(self):
        def do_post(**payload):
            return self.client.post(reverse('manage-backups'), payload, follow=True)

        response = do_post(repository=settings.BACKUP_DIR)
        self.assertContains(response, settings.BACKUP_DIR)
        service = BackupService.objects.get()
        response = do_post(service=service.pk, trigger='1')
        self.assertContains(response, 'triggered')
        response = do_post(service=service.pk, toggle='1')
        self.assertContains(response, 'Turned off')
        response = do_post(service=service.pk, remove='1')
        self.assertNotContains(response, settings.BACKUP_DIR)

    def test_performace(self):
        response = self.client.get(reverse('manage-performance'))
        self.assertContains(response, 'weblate.E005')

    def test_error(self):
        add_configuration_error('Test error', 'FOOOOOOOOOOOOOO')
        response = self.client.get(reverse('manage-performance'))
        self.assertContains(response, 'FOOOOOOOOOOOOOO')
        delete_configuration_error('Test error')
        response = self.client.get(reverse('manage-performance'))
        self.assertNotContains(response, 'FOOOOOOOOOOOOOO')

    def test_report(self):
        response = self.client.get(reverse('manage-repos'))
        self.assertContains(response, 'On branch master')

    def test_create_project(self):
        response = self.client.get(reverse('admin:trans_project_add'))
        self.assertContains(response, 'Required fields are marked in bold')

    def test_create_component(self):
        response = self.client.get(reverse('admin:trans_component_add'))
        self.assertContains(response, 'Import speed documentation')

    def test_component(self):
        """Test for custom component actions."""
        self.assert_custom_admin(reverse('admin:trans_component_changelist'))

    def test_project(self):
        """Test for custom project actions."""
        self.assert_custom_admin(reverse('admin:trans_project_changelist'))

    def assert_custom_admin(self, url):
        """Test for (sub)project custom admin."""
        response = self.client.get(url)
        self.assertContains(response, 'Update VCS repository')
        for action in 'force_commit', 'update_checks', 'update_from_git':
            response = self.client.post(
                url, {'_selected_action': '1', 'action': action}
            )
            self.assertRedirects(response, url)

    def test_configuration_health_check(self):
        add_configuration_error('TEST', 'Message', True)
        add_configuration_error('TEST2', 'Message', True)
        configuration_health_check(False)
        self.assertEqual(ConfigurationError.objects.count(), 2)
        delete_configuration_error('TEST2', True)
        configuration_health_check(False)
        self.assertEqual(ConfigurationError.objects.count(), 1)
        configuration_health_check()

    def test_send_test_email(self, expected='Test e-mail sent'):
        response = self.client.get(reverse('manage-tools'))
        self.assertContains(response, 'e-mail')
        response = self.client.post(
            reverse('manage-tools'), {'email': 'noreply@example.com'}, follow=True
        )
        self.assertContains(response, expected)

    @override_settings(
        EMAIL_HOST='nonexisting.weblate.org',
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
    )
    def test_send_test_email_error(self):
        self.test_send_test_email('Failed to send test e-mail')

    @httpretty.activate
    def test_activation_community(self):
        httpretty.register_uri(
            httpretty.POST,
            settings.SUPPORT_API_URL,
            body=json.dumps(
                {
                    'name': 'community',
                    'backup_repository': '',
                    'expiry': timezone.now(),
                    'in_limits': True,
                },
                cls=DjangoJSONEncoder,
            ),
        )
        self.client.post(reverse('manage-activate'), {'secret': '123456'})
        status = SupportStatus.objects.get()
        self.assertEqual(status.name, 'community')
        self.assertFalse(BackupService.objects.exists())

    @httpretty.activate
    def test_activation_hosted(self):
        httpretty.register_uri(
            httpretty.POST,
            settings.SUPPORT_API_URL,
            body=json.dumps(
                {
                    'name': 'hosted',
                    'backup_repository': '/tmp/xxx',
                    'expiry': timezone.now(),
                    'in_limits': True,
                },
                cls=DjangoJSONEncoder,
            ),
        )
        self.client.post(reverse('manage-activate'), {'secret': '123456'})
        status = SupportStatus.objects.get()
        self.assertEqual(status.name, 'hosted')
        backup = BackupService.objects.get()
        self.assertEqual(backup.repository, '/tmp/xxx')
        self.assertFalse(backup.enabled)
