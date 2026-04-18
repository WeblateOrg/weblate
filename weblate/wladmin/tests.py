# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
from datetime import UTC, datetime, timedelta
from io import StringIO
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import cast
from unittest import TestCase
from unittest.mock import Mock, patch

import responses
from django.conf import settings
from django.core import mail
from django.core.checks import Critical
from django.core.management import call_command
from django.core.serializers.json import DjangoJSONEncoder
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from weblate.accounts.models import AuditLog
from weblate.auth.models import Group, Invitation
from weblate.trans.models import Announcement
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.apps import check_data_writable
from weblate.utils.backup import BackupError, BorgResult
from weblate.utils.data import data_path
from weblate.utils.unittest import tempdir_setting
from weblate.wladmin.forms import ThemeColorField, ThemeColorWidget
from weblate.wladmin.models import BackupService, ConfigurationError, SupportStatus
from weblate.wladmin.tasks import backup_service

TEST_BACKENDS = ("weblate.accounts.auth.WeblateUserBackend",)


class BackupFailureService:
    def __init__(self) -> None:
        self.repository = "/backup"
        self.passphrase = "secret"
        self.backuplog_set = Mock()
        self.ensure_init = Mock(return_value=True)
        self.prune = Mock()
        self.cleanup = Mock()

    def backup(self) -> None:
        BackupService.backup(cast("BackupService", self))

    def create_backup_log(self, event: str, result: BorgResult) -> None:
        BackupService.create_backup_log(cast("BackupService", self), event, result)


class BackupTaskTest(TestCase):
    def test_backup_service_stops_after_init_failure(self) -> None:
        service = Mock()
        service.ensure_init.return_value = False

        with patch(
            "weblate.wladmin.tasks.BackupService.objects.get", return_value=service
        ):
            backup_service(1)

        service.ensure_init.assert_called_once_with()
        service.backup.assert_not_called()
        service.prune.assert_not_called()
        service.cleanup.assert_not_called()

    def test_backup_service_runs_maintenance_after_backup_failure(self) -> None:
        service = BackupFailureService()

        with (
            patch(
                "weblate.wladmin.tasks.BackupService.objects.get",
                return_value=service,
            ),
            patch(
                "weblate.wladmin.models.backup",
                side_effect=BackupError("borg create failed"),
            ),
            patch(
                "weblate.wladmin.tasks.timezone.now",
                return_value=datetime(2026, 3, 26, tzinfo=UTC),
            ),
        ):
            backup_service(1)

        service.ensure_init.assert_called_once_with()
        service.backuplog_set.create.assert_called_once_with(
            event="error", log="borg create failed"
        )
        service.prune.assert_called_once_with()
        service.cleanup.assert_called_once_with()

    def test_backup_service_runs_maintenance_after_success(self) -> None:
        service = Mock()
        service.ensure_init.return_value = True

        with (
            patch(
                "weblate.wladmin.tasks.BackupService.objects.get",
                return_value=service,
            ),
            patch(
                "weblate.wladmin.tasks.timezone.now",
                return_value=datetime(2026, 3, 26, tzinfo=UTC),
            ),
        ):
            backup_service(1)

        service.ensure_init.assert_called_once_with()
        service.backup.assert_called_once_with()
        service.prune.assert_called_once_with()
        service.cleanup.assert_called_once_with()


class BackupServiceStatusTest(TestCase):
    def test_current_error_points_to_latest_unresolved_failure(self) -> None:
        error = SimpleNamespace(event="error", log="borg create failed")
        service = BackupService(repository="/backup")
        service.__dict__["last_logs"] = [
            SimpleNamespace(event="cleanup", log="cleanup complete"),
            SimpleNamespace(event="prune", log="prune complete"),
            error,
        ]

        self.assertTrue(service.has_errors)
        self.assertIs(service.current_error, error)

    def test_current_error_clears_after_successful_backup(self) -> None:
        old_error = SimpleNamespace(event="error", log="old failure")
        service = BackupService(repository="/backup")
        service.__dict__["last_logs"] = [
            SimpleNamespace(event="prune", log="prune complete", warning=False),
            SimpleNamespace(event="backup", log="backup complete", warning=False),
            old_error,
        ]

        self.assertFalse(service.has_errors)
        self.assertIsNone(service.current_error)

    def test_current_error_clears_after_backup_warning(self) -> None:
        old_error = SimpleNamespace(event="error", log="old failure", warning=False)
        warning = SimpleNamespace(
            event="backup", log="backup complete with warnings", warning=True
        )
        service = BackupService(repository="/backup")
        service.__dict__["last_logs"] = [warning, old_error]

        self.assertFalse(service.has_errors)
        self.assertIsNone(service.current_error)
        self.assertTrue(service.has_warnings)
        self.assertIs(service.current_warning, warning)

    def test_current_warning_clears_after_clean_backup(self) -> None:
        old_warning = SimpleNamespace(
            event="backup", log="backup complete with warnings", warning=True
        )
        service = BackupService(repository="/backup")
        service.__dict__["last_logs"] = [
            SimpleNamespace(event="backup", log="backup complete", warning=False),
            old_warning,
        ]

        self.assertFalse(service.has_warnings)
        self.assertIsNone(service.current_warning)

    def test_backup_logs_warning_without_error(self) -> None:
        service = BackupFailureService()

        with patch(
            "weblate.wladmin.models.backup",
            return_value=BorgResult("borg completed with warnings", returncode=1),
        ):
            service.backup()

        service.backuplog_set.create.assert_called_once_with(
            event="backup", log="borg completed with warnings", warning=True
        )


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
        hostsfile = data_path("ssh") / "known_hosts"
        try:
            os.environ["PATH"] = f"{get_test_file('')}:{os.environ['PATH']}"
            # Verify there is button for adding
            response = self.client.get(reverse("manage-ssh"))
            self.assertContains(response, "Add host key")

            # Invalid parameters
            response = self.client.post(
                reverse("manage-ssh"), {"action": "add-host", "host": "-github.com"}
            )
            self.assertContains(response, "Enter a valid domain name or IP address.")
            self.assertFalse(hostsfile.exists())

            # Non-responding host
            response = self.client.post(
                reverse("manage-ssh"), {"action": "add-host", "host": "1.2.3.4"}
            )
            self.assertContains(response, "Could not fetch public key for a host.")
            self.assertFalse(hostsfile.exists())

            # Error response
            response = self.client.post(
                reverse("manage-ssh"),
                {
                    "action": "add-host",
                    "host": "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
                },
            )
            self.assertContains(
                response, "Could not fetch public key for a host: test error"
            )
            self.assertFalse(hostsfile.exists())

            # Do not add not matching key
            response = self.client.post(
                reverse("manage-ssh"),
                {
                    "action": "add-host",
                    "host": "example.com",
                    "fingerprint": "p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM",
                },
            )
            self.assertContains(response, "Skipped host key for example.com")
            self.assertFalse(hostsfile.exists())

            # Add the matching key
            response = self.client.post(
                reverse("manage-ssh"),
                {
                    "action": "add-host",
                    "host": "example.com",
                    "fingerprint": "nThbg6kXUpJWGl7E1IGOCspRomTxdCARLviKw6E5SY8",
                },
            )
            self.assertContains(response, "Added host key for example.com")
            self.assertTrue(hostsfile.exists())

            # Remove the stored key so it can be replaced from the same page
            response = self.client.get(reverse("manage-ssh"))
            host_key_id = response.context["host_keys"][0]["id"]
            response = self.client.post(
                reverse("manage-ssh"),
                {"action": "remove-host", "host_key": host_key_id},
            )
            self.assertContains(response, "Removed host key for example.com")
            self.assertEqual(hostsfile.read_text(), "")

            # Add all the keys
            response = self.client.post(
                reverse("manage-ssh"), {"action": "add-host", "host": "example.com"}
            )
            self.assertContains(response, "Added host key for example.com")
            self.assertTrue(hostsfile.exists())
        finally:
            os.environ["PATH"] = oldpath

        # Check the file contains it
        self.assertIn("example.com", hostsfile.read_text())

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

    def test_performance(self) -> None:
        response = self.client.get(reverse("manage-performance"))
        self.assertContains(response, "weblate.E005")

    def test_performance_ordering(self) -> None:
        with (
            patch(
                "weblate.wladmin.views.run_checks",
                return_value=[
                    Critical(msg="Zulu", id="weblate.E200"),
                    Critical(msg="Alpha", id="weblate.E100"),
                    Critical(msg="Bravo", id="weblate.E100"),
                ],
            ),
            patch(
                "weblate.wladmin.views.get_queue_stats",
                return_value={"zqueue": 1, "aqueue": 2},
            ),
        ):
            response = self.client.get(reverse("manage-performance"))

        checks = [check.id for check in response.context["checks"]]
        self.assertEqual(checks, ["weblate.E100", "weblate.E100", "weblate.E200"])
        self.assertEqual(
            [check.msg for check in response.context["checks"]],
            ["Alpha", "Bravo", "Zulu"],
        )
        self.assertEqual(
            list(response.context["queues"]),
            [("aqueue", 2), ("zqueue", 1)],
        )

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
        self.client.post(
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

    def test_bulk_invite_user(self) -> None:
        response = self.client.post(
            reverse("manage-users"),
            {
                "emails": "noreply@example.com second@example.com invalid second@example.com",
                "group": Group.objects.get(name="Users").pk,
                "is_superuser": "on",
            },
            follow=True,
        )
        self.assertContains(response, "2 invitation e-mails were sent.")
        self.assertContains(response, "Skipped 2 addresses")
        self.assertContains(response, "invalid: Enter a valid e-mail address.")
        self.assertContains(
            response, "second@example.com: duplicate address in the submission"
        )
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(Invitation.objects.count(), 2)
        self.assertEqual(Invitation.objects.filter(is_superuser=True).count(), 2)

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
        self.assertRedirects(response, f"{reverse('manage-users')}?q=nonexisting")

    def test_manage_users_search_by_audit_ip(self) -> None:
        request = self.factory.get("/", REMOTE_ADDR="192.0.2.24")
        request.user = self.user
        AuditLog.objects.create(self.user, request, "login")

        response = self.client.get(reverse("manage-users"), {"q": "192.0.2.24"})

        self.assertContains(response, self.user.get_absolute_url())

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
                    "has_subscription": False,
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
                        "has_subscription": True,
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

            # Toggle discovery
            self.client.post(reverse("manage-discovery"))
            status = SupportStatus.objects.get()
            self.assertTrue(status.discoverable)

            # Use different payload for second registration
            responses.delete(responses.POST, settings.SUPPORT_API_URL)
            responses.add(
                responses.POST,
                settings.SUPPORT_API_URL,
                body=json.dumps(
                    {
                        "name": "hosted",
                        "backup_repository": tempdir,
                        "expiry": timezone.now() - timedelta(days=1),
                        "in_limits": True,
                        "has_subscription": True,
                        "limits": {},
                    },
                    cls=DjangoJSONEncoder,
                ),
            )
            # Changing secret
            self.client.post(reverse("manage-activate"), {"secret": "654321"})
            old_status = SupportStatus.objects.get(pk=status.pk)
            self.assertFalse(old_status.enabled)
            new_status = SupportStatus.objects.filter(enabled=True).get()
            self.assertEqual(new_status.name, "hosted")
            self.assertEqual(SupportStatus.objects.get_current(), new_status)

            # Refresh
            self.client.post(reverse("manage-activate"), {"refresh": "1"})
            new_status = SupportStatus.objects.get_current()
            self.assertEqual(new_status.name, "hosted")
            self.assertTrue(new_status.enabled)

            # Unlink
            self.client.post(reverse("manage-activate"), {"unlink": "1"})
            self.assertFalse(SupportStatus.objects.filter(enabled=True).exists())
            new_status = SupportStatus.objects.get_current()
            self.assertEqual(new_status.pk, None)
            self.assertEqual(new_status.name, "community")
            self.assertFalse(new_status.enabled)

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
        data_list: list[str] = []
        expected = None
        self.assertEqual(self.field.compress(data_list), expected)
