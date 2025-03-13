# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
from io import StringIO
from tempfile import TemporaryDirectory
from unittest import TestCase

import responses
from django.conf import settings
from django.core import mail
from django.core.checks import Critical
from django.core.management import call_command
from django.core.serializers.json import DjangoJSONEncoder
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from weblate.auth.models import Group
from weblate.trans.models import Announcement
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.apps import check_data_writable
from weblate.utils.unittest import tempdir_setting
from weblate.wladmin.forms import ThemeColorField, ThemeColorWidget
from weblate.wladmin.models import BackupService, ConfigurationError, SupportStatus

TEST_BACKENDS = ("weblate.accounts.auth.WeblateUserBackend",)


class AdminTest(ViewTestCase):
    """Test for customized admin interface."""

    def setUp(self) -> None:
        super().setUp()
        self.user.is_superuser = True
        self.user.save()

    def test_index(self) -> None:
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "SSH")

    def test_manage_index(self) -> None:
        response = self.client.get(reverse("manage"))
        self.assertContains(response, "SSH")

    def test_ssh(self) -> None:
        response = self.client.get(reverse("manage-ssh"))
        self.assertContains(response, "SSH keys")

    @tempdir_setting("DATA_DIR")
    def test_ssh_generate(self) -> None:
        self.assertEqual(check_data_writable(app_configs=None, databases=None), [])
        response = self.client.get(reverse("manage-ssh"))
        self.assertContains(response, "Generate RSA SSH key")
        self.assertContains(response, "Generate Ed25519 SSH key")

        response = self.client.post(
            reverse("manage-ssh"), {"action": "generate"}, follow=True
        )
        self.assertContains(response, "Created new SSH key")
        response = self.client.get(reverse("manage-ssh-key"))
        self.assertContains(response, "PRIVATE KEY")
        response = self.client.get(reverse("manage-ssh-key"), {"type": "rsa"})
        self.assertContains(response, "PRIVATE KEY")

        response = self.client.post(
            reverse("manage-ssh"),
            {"action": "generate", "type": "ed25519"},
            follow=True,
        )
        self.assertContains(response, "Created new SSH key")
        response = self.client.get(reverse("manage-ssh-key"), {"type": "ed25519"})
        self.assertContains(response, "PRIVATE KEY")

    @tempdir_setting("DATA_DIR")
    def test_ssh_add(self) -> None:
        self.assertEqual(check_data_writable(app_configs=None, databases=None), [])
        oldpath = os.environ["PATH"]
        try:
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
    def test_backup(self) -> None:
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

    def test_performace(self) -> None:
        response = self.client.get(reverse("manage-performance"))
        self.assertContains(response, "weblate.E005")

    def test_error(self) -> None:
        ConfigurationError.objects.create(name="Test error", message="FOOOOOOOOOOOOOO")
        response = self.client.get(reverse("manage-performance"))
        self.assertContains(response, "FOOOOOOOOOOOOOO")
        ConfigurationError.objects.filter(name="Test error").delete()
        response = self.client.get(reverse("manage-performance"))
        self.assertNotContains(response, "FOOOOOOOOOOOOOO")

    def test_report(self) -> None:
        response = self.client.get(reverse("manage-repos"))
        self.assertContains(response, "On branch main")

    def test_create_project(self) -> None:
        response = self.client.get(reverse("admin:trans_project_add"))
        self.assertContains(response, "Required fields are marked in bold")

    def test_create_component(self) -> None:
        response = self.client.get(reverse("admin:trans_component_add"))
        self.assertContains(response, "Import speed documentation")

    def test_component(self) -> None:
        """Test for custom component actions."""
        self.assert_custom_admin(reverse("admin:trans_component_changelist"))

    def test_project(self) -> None:
        """Test for custom project actions."""
        self.assert_custom_admin(reverse("admin:trans_project_changelist"))

    def assert_custom_admin(self, url) -> None:
        """Test for (sub)project custom admin."""
        response = self.client.get(url)
        self.assertContains(response, "Update VCS repository")
        for action in "force_commit", "update_checks", "update_from_git":
            response = self.client.post(
                url, {"_selected_action": "1", "action": action}
            )
            self.assertRedirects(response, url)

    def test_configuration_health_check(self) -> None:
        # Run checks internally
        ConfigurationError.objects.configuration_health_check()
        # List of triggered checks remotely
        ConfigurationError.objects.configuration_health_check(
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
        ConfigurationError.objects.configuration_health_check([])
        self.assertEqual(ConfigurationError.objects.count(), 0)

    def test_post_announcement(self) -> None:
        response = self.client.get(reverse("manage-tools"))
        self.assertContains(response, "announcement")
        self.assertFalse(Announcement.objects.exists())
        response = self.client.post(
            reverse("manage-tools"),
            {"message": "Test message", "severity": "info"},
            follow=True,
        )
        self.assertTrue(Announcement.objects.exists())

    def test_send_test_email(self, expected="Test e-mail sent") -> None:
        response = self.client.get(reverse("manage-tools"))
        self.assertContains(response, "e-mail")
        response = self.client.post(
            reverse("manage-tools"), {"email": "noreply@example.com"}, follow=True
        )
        self.assertContains(response, expected)
        if expected == "Test e-mail sent":
            self.assertEqual(len(mail.outbox), 1)

    def test_invite_user(self) -> None:
        response = self.client.get(reverse("manage-users"))
        self.assertContains(response, "E-mail")
        response = self.client.post(
            reverse("manage-users"),
            {
                "email": "noreply@example.com",
                "group": Group.objects.get(name="Users").pk,
            },
            follow=True,
        )
        self.assertContains(response, "User invitation e-mail was sent")
        self.assertEqual(len(mail.outbox), 1)

    def test_check_user(self) -> None:
        response = self.client.get(
            reverse("manage-users-check"), {"q": self.user.email}, follow=True
        )
        self.assertRedirects(response, self.user.get_absolute_url())
        response = self.client.get(
            reverse("manage-users-check"), {"email": self.user.email}, follow=True
        )
        self.assertRedirects(response, self.user.get_absolute_url())
        self.assertContains(response, "Never signed-in")
        response = self.client.get(
            reverse("manage-users-check"), {"email": "nonexisting"}, follow=True
        )
        self.assertRedirects(response, reverse("manage-users") + "?q=nonexisting")

    @override_settings(
        EMAIL_HOST="nonexisting.weblate.org",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    )
    def test_send_test_email_error(self) -> None:
        self.test_send_test_email("Could not send test e-mail")

    @responses.activate
    @override_settings(SITE_TITLE="Test Weblate")
    def test_activation_wrong(self) -> None:
        responses.add(
            responses.POST,
            settings.SUPPORT_API_URL,
            status=404,
        )
        response = self.client.post(
            reverse("manage-activate"), {"secret": "123456"}, follow=True
        )
        self.assertContains(response, "Please ensure your activation token is correct.")
        self.assertFalse(SupportStatus.objects.exists())
        self.assertFalse(BackupService.objects.exists())

    @responses.activate
    @override_settings(SITE_TITLE="Test Weblate")
    def test_activation_error(self) -> None:
        responses.add(
            responses.POST,
            settings.SUPPORT_API_URL,
            status=500,
        )
        response = self.client.post(
            reverse("manage-activate"), {"secret": "123456"}, follow=True
        )
        self.assertContains(response, "Please try again later.")
        self.assertFalse(SupportStatus.objects.exists())
        self.assertFalse(BackupService.objects.exists())

    @responses.activate
    @override_settings(SITE_TITLE="Test Weblate")
    def test_activation_community(self) -> None:
        responses.add(
            responses.POST,
            settings.SUPPORT_API_URL,
            body=json.dumps(
                {
                    "name": "community",
                    "backup_repository": "",
                    "expiry": timezone.now(),
                    "in_limits": True,
                    "limits": {},
                },
                cls=DjangoJSONEncoder,
            ),
        )
        self.client.post(reverse("manage-activate"), {"secret": "123456"})
        status = SupportStatus.objects.get()
        self.assertEqual(status.name, "community")
        self.assertFalse(BackupService.objects.exists())

        self.assertFalse(status.discoverable)

        self.client.post(reverse("manage-discovery"))
        status = SupportStatus.objects.get()
        self.assertTrue(status.discoverable)

    @responses.activate
    @override_settings(SITE_TITLE="Test Weblate")
    def test_activation_hosted(self) -> None:
        with TemporaryDirectory() as tempdir:
            responses.add(
                responses.POST,
                settings.SUPPORT_API_URL,
                body=json.dumps(
                    {
                        "name": "hosted",
                        "backup_repository": tempdir,
                        "expiry": timezone.now(),
                        "in_limits": True,
                        "limits": {},
                    },
                    cls=DjangoJSONEncoder,
                ),
            )
            self.client.post(reverse("manage-activate"), {"secret": "123456"})
            status = SupportStatus.objects.get()
            self.assertEqual(status.name, "hosted")
            backup = BackupService.objects.get()
            self.assertEqual(backup.repository, tempdir)
            self.assertFalse(backup.enabled)

            self.assertFalse(status.discoverable)

            self.client.post(reverse("manage-discovery"))
            status = SupportStatus.objects.get()
            self.assertTrue(status.discoverable)

    def test_group_management(self) -> None:
        # Add form
        response = self.client.get(reverse("admin:weblate_auth_group_add"))
        self.assertContains(response, "Automatic team assignment")

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
        self.assertContains(response, "Automatic team assignment")
        self.assertContains(response, name)

    def test_groups(self) -> None:
        name = "Test group"
        url = reverse("manage-teams")
        response = self.client.get(url)
        self.assertNotContains(response, name)

        # Create
        response = self.client.post(
            reverse("manage-teams"),
            {
                "name": name,
                "language_selection": "1",
                "project_selection": "1",
            },
        )
        self.assertRedirects(response, url)
        response = self.client.get(url)
        self.assertContains(response, name)

        # Edit
        group = Group.objects.get(name=name)
        response = self.client.post(
            group.get_absolute_url(),
            {
                "name": name,
                "language_selection": "1",
                "project_selection": "1",
                "autogroup_set-TOTAL_FORMS": "1",
                "autogroup_set-INITIAL_FORMS": "0",
                "autogroup_set-0-match": "^.*$",
            },
        )
        self.assertRedirects(response, group.get_absolute_url())
        group = Group.objects.get(name=name)

        self.assertEqual(group.autogroup_set.count(), 1)

        # Delete
        response = self.client.post(
            group.get_absolute_url(),
            {
                "delete": 1,
            },
        )
        self.assertRedirects(response, url)

        response = self.client.get(url)
        self.assertNotContains(response, name)

    def test_edit_internal_group(self) -> None:
        response = self.client.post(
            Group.objects.get(name="Users").get_absolute_url(),
            {
                "name": "Other",
                "language_selection": "1",
                "project_selection": "1",
            },
        )
        self.assertContains(response, "Cannot change this on a built-in team")

    def test_commands(self) -> None:
        out = StringIO()
        call_command("configuration_health_check", stdout=out)
        self.assertEqual(out.getvalue(), "")


class TestThemeColorField(TestCase):
    """Tests for ThemeColorField widget."""

    def setUp(self) -> None:
        self.field = ThemeColorField()
        self.widget = ThemeColorWidget()

    def test_decompress_two_colors(self) -> None:
        value = "#ffffff,#000000"
        expected = ["#ffffff", "#000000"]
        self.assertEqual(self.widget.decompress(value), expected)

    def test_decompress_one_color(self) -> None:
        value = "#ffffff"
        expected = ["#ffffff", "#ffffff"]
        self.assertEqual(self.widget.decompress(value), expected)

    def test_decompress_no_value(self) -> None:
        value = None
        expected = [None, None]
        self.assertEqual(self.widget.decompress(value), expected)

    def test_compress_two_colors(self) -> None:
        data_list = ["#ffffff", "#000000"]
        expected = "#ffffff,#000000"
        self.assertEqual(self.field.compress(data_list), expected)

    def test_compress_one_color(self) -> None:
        data_list = ["#ffffff", "#ffffff"]
        expected = "#ffffff,#ffffff"
        self.assertEqual(self.field.compress(data_list), expected)

    def test_compress_no_data(self) -> None:
        data_list = []
        expected = None
        self.assertEqual(self.field.compress(data_list), expected)
