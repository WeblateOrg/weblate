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

import json
import os

import responses
from django.conf import settings
from django.core import mail
from django.core.checks import Critical
from django.core.serializers.json import DjangoJSONEncoder
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from weblate.auth.models import Group
from weblate.trans.models import Announcement
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.checks import check_data_writable
from weblate.utils.unittest import tempdir_setting
from weblate.wladmin.models import BackupService, ConfigurationError, SupportStatus
from weblate.wladmin.tasks import configuration_health_check


class AdminTest(ViewTestCase):
    """Test for customized admin interface."""

    def setUp(self):
        super().setUp()
        self.user.is_superuser = True
        self.user.save()

    def test_index(self):
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "SSH")

    def test_manage_index(self):
        response = self.client.get(reverse("manage"))
        self.assertContains(response, "SSH")

    def test_ssh(self):
        response = self.client.get(reverse("manage-ssh"))
        self.assertContains(response, "SSH keys")

    @tempdir_setting("DATA_DIR")
    def test_ssh_generate(self):
        self.assertEqual(check_data_writable(), [])
        response = self.client.get(reverse("manage-ssh"))
        self.assertContains(response, "Generate SSH key")

        response = self.client.post(reverse("manage-ssh"), {"action": "generate"})
        self.assertContains(response, "Created new SSH key")
        response = self.client.get(reverse("manage-ssh-key"))
        self.assertContains(response, "PRIVATE KEY")

    @tempdir_setting("DATA_DIR")
    def test_ssh_add(self):
        self.assertEqual(check_data_writable(), [])
        try:
            oldpath = os.environ["PATH"]
            os.environ["PATH"] = ":".join((get_test_file(""), os.environ["PATH"]))
            # Verify there is button for adding
            response = self.client.get(reverse("manage-ssh"))
            self.assertContains(response, "Add host key")

            # Add the key
            response = self.client.post(
                reverse("manage-ssh"), {"action": "add-host", "host": "github.com"}
            )
            self.assertContains(response, "Added host key for github.com")
        finally:
            os.environ["PATH"] = oldpath

        # Check the file contains it
        hostsfile = os.path.join(settings.DATA_DIR, "ssh", "known_hosts")
        with open(hostsfile) as handle:
            self.assertIn("github.com", handle.read())

    @tempdir_setting("BACKUP_DIR")
    def test_backup(self):
        def do_post(**payload):
            return self.client.post(reverse("manage-backups"), payload, follow=True)

        response = do_post(repository=settings.BACKUP_DIR)
        self.assertContains(response, settings.BACKUP_DIR)
        service = BackupService.objects.get()
        response = do_post(service=service.pk, trigger="1")
        self.assertContains(response, "triggered")
        response = do_post(service=service.pk, toggle="1")
        self.assertContains(response, "Turned off")
        response = do_post(service=service.pk, remove="1")
        self.assertNotContains(response, settings.BACKUP_DIR)

    def test_performace(self):
        response = self.client.get(reverse("manage-performance"))
        self.assertContains(response, "weblate.E005")

    def test_error(self):
        ConfigurationError.objects.create(name="Test error", message="FOOOOOOOOOOOOOO")
        response = self.client.get(reverse("manage-performance"))
        self.assertContains(response, "FOOOOOOOOOOOOOO")
        ConfigurationError.objects.filter(name="Test error").delete()
        response = self.client.get(reverse("manage-performance"))
        self.assertNotContains(response, "FOOOOOOOOOOOOOO")

    def test_report(self):
        response = self.client.get(reverse("manage-repos"))
        self.assertContains(response, "On branch master")

    def test_create_project(self):
        response = self.client.get(reverse("admin:trans_project_add"))
        self.assertContains(response, "Required fields are marked in bold")

    def test_create_component(self):
        response = self.client.get(reverse("admin:trans_component_add"))
        self.assertContains(response, "Import speed documentation")

    def test_component(self):
        """Test for custom component actions."""
        self.assert_custom_admin(reverse("admin:trans_component_changelist"))

    def test_project(self):
        """Test for custom project actions."""
        self.assert_custom_admin(reverse("admin:trans_project_changelist"))

    def assert_custom_admin(self, url):
        """Test for (sub)project custom admin."""
        response = self.client.get(url)
        self.assertContains(response, "Update VCS repository")
        for action in "force_commit", "update_checks", "update_from_git":
            response = self.client.post(
                url, {"_selected_action": "1", "action": action}
            )
            self.assertRedirects(response, url)

    def test_configuration_health_check(self):
        # Run checks internally
        configuration_health_check()
        # List of triggered checks remotely
        configuration_health_check(
            [
                Critical(msg="Error", id="weblate.E001"),
                Critical(msg="Test Error", id="weblate.E002"),
            ]
        )
        all_errors = ConfigurationError.objects.all()
        self.assertEqual(len(all_errors), 1)
        self.assertEqual(all_errors[0].name, "weblate.E002")
        self.assertEqual(all_errors[0].message, "Test Error")
        # No triggered checks
        configuration_health_check([])
        self.assertEqual(ConfigurationError.objects.count(), 0)

    def test_post_announcenement(self):
        response = self.client.get(reverse("manage-tools"))
        self.assertContains(response, "announcement")
        self.assertFalse(Announcement.objects.exists())
        response = self.client.post(
            reverse("manage-tools"),
            {"message": "Test message", "category": "info"},
            follow=True,
        )
        self.assertTrue(Announcement.objects.exists())

    def test_send_test_email(self, expected="Test e-mail sent"):
        response = self.client.get(reverse("manage-tools"))
        self.assertContains(response, "e-mail")
        response = self.client.post(
            reverse("manage-tools"), {"email": "noreply@example.com"}, follow=True
        )
        self.assertContains(response, expected)
        if expected == "Test e-mail sent":
            self.assertEqual(len(mail.outbox), 1)

    def test_invite_user(self):
        response = self.client.get(reverse("manage-users"))
        self.assertContains(response, "E-mail")
        response = self.client.post(
            reverse("manage-users"),
            {
                "email": "noreply@example.com",
                "username": "username",
                "full_name": "name",
            },
            follow=True,
        )
        self.assertContains(response, "User has been invited")
        self.assertEqual(len(mail.outbox), 1)

    def test_check_user(self):
        response = self.client.get(
            reverse("manage-users-check"), {"email": self.user.email}
        )
        self.assertContains(response, "Last login")

    @override_settings(
        EMAIL_HOST="nonexisting.weblate.org",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    )
    def test_send_test_email_error(self):
        self.test_send_test_email("Could not send test e-mail")

    @responses.activate
    def test_activation_community(self):
        responses.add(
            responses.POST,
            settings.SUPPORT_API_URL,
            body=json.dumps(
                {
                    "name": "community",
                    "backup_repository": "",
                    "expiry": timezone.now(),
                    "in_limits": True,
                },
                cls=DjangoJSONEncoder,
            ),
        )
        self.client.post(reverse("manage-activate"), {"secret": "123456"})
        status = SupportStatus.objects.get()
        self.assertEqual(status.name, "community")
        self.assertFalse(BackupService.objects.exists())

    @responses.activate
    def test_activation_hosted(self):
        responses.add(
            responses.POST,
            settings.SUPPORT_API_URL,
            body=json.dumps(
                {
                    "name": "hosted",
                    "backup_repository": "/tmp/xxx",
                    "expiry": timezone.now(),
                    "in_limits": True,
                },
                cls=DjangoJSONEncoder,
            ),
        )
        self.client.post(reverse("manage-activate"), {"secret": "123456"})
        status = SupportStatus.objects.get()
        self.assertEqual(status.name, "hosted")
        backup = BackupService.objects.get()
        self.assertEqual(backup.repository, "/tmp/xxx")
        self.assertFalse(backup.enabled)

    def test_group_management(self):
        # Add form
        response = self.client.get(reverse("admin:weblate_auth_group_add"))
        self.assertContains(response, "Automatic group assignment")

        # Create group
        name = "Test group"
        response = self.client.post(
            reverse("admin:weblate_auth_group_add"),
            {
                "name": name,
                "language_selection": "1",
                "project_selection": "1",
                "autogroup_set-TOTAL_FORMS": "0",
                "autogroup_set-INITIAL_FORMS": "0",
            },
            follow=True,
        )
        self.assertContains(response, name)

        # Edit form
        group = Group.objects.get(name=name)
        url = reverse("admin:weblate_auth_group_change", kwargs={"object_id": group.pk})
        response = self.client.get(url)
        self.assertContains(response, "Automatic group assignment")
        self.assertContains(response, name)
