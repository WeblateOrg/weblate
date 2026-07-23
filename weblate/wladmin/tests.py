# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from io import StringIO
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import cast
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import responses
from django.conf import settings
from django.core import mail
from django.core.checks import Critical
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.test import TestCase as DjangoTestCase
from django.test.utils import CaptureQueriesContext, modify_settings, override_settings
from django.urls import reverse
from django.utils import timezone

from weblate.accounts.models import AuditLog
from weblate.auth.models import Group, Invitation, Permission, Role
from weblate.memory.models import Memory, MemoryScope, MemoryScopeMigrationState
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Announcement, Change, Project
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.apps import check_data_writable
from weblate.utils.backup import BackupError, BorgResult
from weblate.utils.data import data_path
from weblate.utils.unittest import tempdir_setting
from weblate.wladmin.forms import ThemeColorField, ThemeColorWidget
from weblate.wladmin.middleware import (
    CHECK_ATTEMPT_CACHE_KEY,
    CHECK_ATTEMPT_TIMEOUT,
    CHECK_CACHE_KEY,
    CHECK_INTERVAL,
    CHECK_POLL_INTERVAL,
    ManageMiddleware,
    claim_configuration_health_check,
    perform_configuration_health_check,
    run_background_configuration_health_check,
)
from weblate.wladmin.models import (
    BackupService,
    ConfigurationError,
    SupportStatus,
    get_support_url,
)
from weblate.wladmin.tasks import backup_service
from weblate.wladmin.views import (
    DISCOVERY_REGISTRATION_SESSION,
    DISCOVERY_REGISTRATION_STATE_AGE,
    get_discovery_site_url,
)
from weblate.workspaces.models import Workspace

TEST_BACKENDS = ("weblate.accounts.auth.WeblateUserBackend",)


def get_response_call_body(index: int) -> str:
    request_body = responses.calls[index].request.body
    if isinstance(request_body, bytes):
        return request_body.decode()
    assert isinstance(request_body, str)
    return request_body


@contextmanager
def restored_environment(name: str, value: str):
    try:
        yield
    finally:
        os.environ[name] = value


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


class BackupCommandTest(DjangoTestCase):
    def test_list_services(self) -> None:
        enabled = BackupService.objects.create(
            repository="/backup/enabled", paperkey="paper"
        )
        disabled = BackupService.objects.create(
            repository="/backup/disabled", enabled=False, paperkey="paper"
        )

        output = StringIO()
        call_command("backup", "--list", stdout=output)

        self.assertEqual(
            output.getvalue().splitlines(),
            [
                f"{enabled.pk}\tenabled\t/backup/enabled",
                f"{disabled.pk}\tdisabled\t/backup/disabled",
            ],
        )

    def test_service_runs_synchronously(self) -> None:
        service = BackupService.objects.create(repository="/backup", paperkey="paper")

        with (
            patch(
                "weblate.wladmin.management.commands.backup.run_settings_backup"
            ) as settings_backup,
            patch(
                "weblate.wladmin.management.commands.backup.run_database_backup"
            ) as database_backup,
            patch(
                "weblate.wladmin.management.commands.backup.run_backup_service"
            ) as backup_service_runner,
        ):
            call_command("backup", "--service", str(service.pk))

        settings_backup.assert_called_once_with()
        database_backup.assert_called_once_with()
        backup_service_runner.assert_called_once_with(service)

    def test_all_runs_enabled_services_synchronously(self) -> None:
        enabled = BackupService.objects.create(
            repository="/backup/enabled", paperkey="paper"
        )
        BackupService.objects.create(
            repository="/backup/disabled", enabled=False, paperkey="paper"
        )

        with (
            patch(
                "weblate.wladmin.management.commands.backup.run_settings_backup"
            ) as settings_backup,
            patch(
                "weblate.wladmin.management.commands.backup.run_database_backup"
            ) as database_backup,
            patch(
                "weblate.wladmin.management.commands.backup.run_backup_service"
            ) as backup_service_runner,
        ):
            call_command("backup", "--all")

        settings_backup.assert_called_once_with()
        database_backup.assert_called_once_with()
        self.assertEqual(
            [call.args[0].pk for call in backup_service_runner.call_args_list],
            [enabled.pk],
        )

    def test_all_reports_failed_services(self) -> None:
        first = BackupService.objects.create(repository="/backup/one", paperkey="paper")
        second = BackupService.objects.create(
            repository="/backup/two", paperkey="paper"
        )

        with (
            patch("weblate.wladmin.management.commands.backup.run_settings_backup"),
            patch("weblate.wladmin.management.commands.backup.run_database_backup"),
            patch(
                "weblate.wladmin.management.commands.backup.run_backup_service",
                side_effect=[False, True],
            ) as backup_service_runner,
            self.assertRaisesRegex(CommandError, f"Backup service failed: {first.pk}"),
        ):
            call_command("backup", "--all")

        self.assertEqual(
            [call.args[0].pk for call in backup_service_runner.call_args_list],
            [first.pk, second.pk],
        )

    def test_verbosity_outputs_service_logs(self) -> None:
        service = BackupService.objects.create(repository="/backup", paperkey="paper")

        def run_backup(service: BackupService) -> bool:
            service.backuplog_set.create(event="backup", log="borg backup output")
            return True

        output = StringIO()
        with (
            patch("weblate.wladmin.management.commands.backup.run_settings_backup"),
            patch("weblate.wladmin.management.commands.backup.run_database_backup"),
            patch(
                "weblate.wladmin.management.commands.backup.run_backup_service",
                side_effect=run_backup,
            ),
        ):
            call_command(
                "backup", "--service", str(service.pk), verbosity=2, stdout=output
            )

        self.assertIn(f"Backup service {service.pk}: /backup", output.getvalue())
        self.assertIn("borg backup output", output.getvalue())

    def test_error_outputs_service_logs(self) -> None:
        service = BackupService.objects.create(repository="/backup", paperkey="paper")

        def run_backup(service: BackupService) -> bool:
            service.backuplog_set.create(event="error", log="borg failed")
            return True

        output = StringIO()
        with (
            patch("weblate.wladmin.management.commands.backup.run_settings_backup"),
            patch("weblate.wladmin.management.commands.backup.run_database_backup"),
            patch(
                "weblate.wladmin.management.commands.backup.run_backup_service",
                side_effect=run_backup,
            ),
            self.assertRaisesRegex(
                CommandError, f"Backup service failed: {service.pk}"
            ),
        ):
            call_command("backup", "--service", str(service.pk), stderr=output)

        self.assertIn(f"Backup service {service.pk}: /backup", output.getvalue())
        self.assertIn("borg failed", output.getvalue())

    def test_rejects_conflicting_selection(self) -> None:
        with self.assertRaises(CommandError):
            call_command("backup", "--all", "--service", "1")

    def test_rejects_unknown_service(self) -> None:
        with self.assertRaisesRegex(CommandError, "Backup service 1 does not exist"):
            call_command("backup", "--service", "1")


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


class WorkspaceCreateTest(ViewTestCase):
    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_workspace_add_denied_without_permission(self) -> None:
        response = self.client.get(reverse("manage-workspace-add"))

        self.assertEqual(response.status_code, 403)

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_project_creator_can_add_workspace(self) -> None:
        self.user.groups.add(Group.objects.get(name="Project creators"))

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Add new workspace")

        response = self.client.get(reverse("manage-workspace-add"))
        self.assertContains(response, "Add workspace")

        response = self.client.post(
            reverse("manage-workspace-add"), {"name": "Created workspace"}
        )

        workspace = Workspace.objects.get(name="Created workspace")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], workspace.get_absolute_url())
        self.user.clear_permissions_cache()
        self.assertTrue(self.user.has_perm("workspace.edit", workspace))
        self.assertTrue(self.user.has_perm("workspace.add_project", workspace))

        response = self.client.get(workspace.get_absolute_url())
        self.assertContains(response, "Created workspace")

        change = Change.objects.get(
            action=ActionEvents.CREATE_WORKSPACE, workspace=workspace
        )
        self.assertEqual(change.user, self.user)
        self.assertEqual(change.author, self.user)


class ManagementAccessControlTest(ViewTestCase):
    """Test site-wide permission checks in the management interface."""

    def grant_global_permissions(
        self, *permissions: str, enforced_2fa: bool = False
    ) -> None:
        role, _created = Role.objects.get_or_create(name="Test management role")
        permission_objects = list(Permission.objects.filter(codename__in=permissions))
        self.assertEqual(
            {permission.codename for permission in permission_objects},
            set(permissions),
        )
        role.permissions.add(*permission_objects)
        group, _created = Group.objects.get_or_create(name="Test management team")
        group.enforced_2fa = enforced_2fa
        group.save(update_fields=["enforced_2fa"])
        group.roles.add(role)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

    def assert_forbidden(self, url_name: str, method: str = "get", **kwargs) -> None:
        response = getattr(self.client, method)(reverse(url_name), **kwargs)
        self.assertEqual(response.status_code, 403)

    def test_management_use_only_is_limited(self) -> None:
        self.grant_global_permissions("management.use")
        email = cast("str", self.user.email)

        response = self.client.get(reverse("manage"))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("manage-performance"))
        self.assertEqual(response.status_code, 200)

        for url_name in (
            "manage-users",
            "manage-teams",
            "manage-memory",
            "manage-memory-download",
            "manage-machinery",
            "manage-addons",
            "manage-backups",
            "manage-ssh",
            "manage-ssh-key",
            "manage-appearance",
            "manage-billing",
        ):
            self.assert_forbidden(url_name)

        self.assert_forbidden("manage-users-check", data={"q": email})
        self.assert_forbidden("manage-activate", method="post", data={"refresh": "1"})
        self.assert_forbidden("manage-discovery", method="post", data={})
        self.assert_forbidden(
            "manage-performance", method="post", data={"pk": "1", "ignore": "1"}
        )

    def test_management_use_requires_enforced_2fa(self) -> None:
        self.grant_global_permissions("management.use", enforced_2fa=True)

        response = self.client.get(reverse("manage"))

        self.assertEqual(response.status_code, 403)

    def test_user_view_does_not_allow_user_changes(self) -> None:
        self.grant_global_permissions("management.use", "user.view")
        email = cast("str", self.user.email)

        response = self.client.get(reverse("manage-users"))
        self.assertContains(response, "Manage users")
        self.assertNotContains(response, "Add new user")

        response = self.client.post(
            reverse("manage-users"),
            {
                "email": "noreply@example.com",
                "group": Group.objects.get(name="Users").pk,
            },
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.get(reverse("manage-users-check"), {"q": email})
        self.assertEqual(response.status_code, 403)

    def test_user_edit_allows_user_changes(self) -> None:
        self.grant_global_permissions("management.use", "user.view", "user.edit")

        response = self.client.get(reverse("manage-users"))
        self.assertContains(response, "Add new user")

        response = self.client.post(
            reverse("manage-users"),
            {
                "email": "noreply@example.com",
                "group": Group.objects.get(name="Users").pk,
            },
            follow=True,
        )
        self.assertContains(response, "User invitation e-mail was sent")
        self.assertEqual(Invitation.objects.count(), 1)

    def test_user_edit_requires_management_access_on_direct_user_actions(self) -> None:
        self.grant_global_permissions("user.edit")

        with patch(
            "weblate.accounts.views.cleanup_user_contributions_task.delay"
        ) as mocked_delay:
            response = self.client.post(
                self.anotheruser.get_absolute_url(),
                {
                    "cleanup_user_contributions": "1",
                    "delete_comments": "on",
                },
            )

        self.assertEqual(response.status_code, 403)
        mocked_delay.assert_not_called()

        self.grant_global_permissions("management.use")

        with patch(
            "weblate.accounts.views.cleanup_user_contributions_task.delay"
        ) as mocked_delay:
            response = self.client.post(
                self.anotheruser.get_absolute_url(),
                {
                    "cleanup_user_contributions": "1",
                    "delete_comments": "on",
                },
            )

        self.assertEqual(response.status_code, 302)
        mocked_delay.assert_called_once_with(
            target_user_id=self.anotheruser.id,
            acting_user_id=self.user.id,
            sitewide=True,
            reject_suggestions=False,
            delete_comments=True,
        )

    def test_user_edit_requires_management_access_on_direct_invitations(self) -> None:
        self.grant_global_permissions("user.edit")
        invitation = Invitation.objects.create(
            author=self.user,
            group=Group.objects.get(name="Users"),
            email="noreply@example.com",
        )

        response = self.client.post(
            invitation.get_absolute_url(),
            {"action": "remove"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Invitation.objects.filter(pk=invitation.pk).exists())

        self.grant_global_permissions("management.use")

        response = self.client.post(
            invitation.get_absolute_url(),
            {"action": "remove"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())

    def test_group_view_does_not_allow_team_changes(self) -> None:
        self.grant_global_permissions("management.use", "group.view")

        response = self.client.get(reverse("manage-teams"))
        self.assertContains(response, "Manage teams")
        self.assertNotContains(response, "Create new team")

        response = self.client.post(reverse("manage-teams"), {"name": "Custom team"})
        self.assertEqual(response.status_code, 403)

    def test_group_edit_allows_team_changes(self) -> None:
        self.grant_global_permissions("management.use", "group.edit")

        response = self.client.get(reverse("manage-teams"))
        self.assertContains(response, "Create new team")

        response = self.client.post(
            reverse("manage-teams"),
            {
                "name": "Custom team",
                "project_selection": "1",
                "language_selection": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Group.objects.filter(name="Custom team").exists())

    def test_group_edit_requires_management_access_on_direct_sitewide_team(
        self,
    ) -> None:
        self.grant_global_permissions("group.edit")
        group = Group.objects.create(name="Custom team")
        edit_payload = {
            "name": "Renamed team",
            "language_selection": "1",
            "project_selection": "1",
            "autogroup_set-TOTAL_FORMS": "0",
            "autogroup_set-INITIAL_FORMS": "0",
        }

        response = self.client.get(group.get_absolute_url())
        self.assertEqual(response.status_code, 403)

        response = self.client.post(group.get_absolute_url(), edit_payload)
        self.assertEqual(response.status_code, 403)
        group.refresh_from_db()
        self.assertEqual(group.name, "Custom team")

        self.grant_global_permissions("management.use")

        response = self.client.post(group.get_absolute_url(), edit_payload)
        self.assertEqual(response.status_code, 302)
        group.refresh_from_db()
        self.assertEqual(group.name, "Renamed team")

    def test_specialized_management_permissions_allow_views(self) -> None:
        self.grant_global_permissions(
            "management.use",
            "management.configure",
            "memory.manage",
            "machinery.edit",
            "billing.manage",
            "management.addons",
            "announcement.edit",
        )

        for url_name in (
            "manage-backups",
            "manage-ssh",
            "manage-appearance",
            "manage-memory",
            "manage-memory-download",
            "manage-machinery",
            "manage-addons",
            "manage-billing",
        ):
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("manage-tools"))
        self.assertContains(response, "Post announcement")
        self.assertContains(response, "Send test e-mail")

        response = self.client.post(
            reverse("manage-tools"), {"email": "noreply@example.com"}, follow=True
        )
        self.assertContains(response, "Test e-mail sent")

        ConfigurationError.objects.create(name="Test error", message="Test error")
        error = ConfigurationError.objects.get()
        response = self.client.post(
            reverse("manage-performance"),
            {"pk": error.pk, "ignore": "1"},
        )
        self.assertEqual(response.status_code, 302)
        error.refresh_from_db()
        self.assertTrue(error.ignored)

    def test_tools_without_announcement_permission(self) -> None:
        self.grant_global_permissions("management.use")

        response = self.client.get(reverse("manage-tools"))
        self.assertNotContains(response, "Send test e-mail")
        self.assertNotContains(response, "Post announcement")

        response = self.client.post(
            reverse("manage-tools"), {"email": "noreply@example.com"}
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(reverse("manage-tools"), {"sentry": "1"})
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("manage-tools"),
            {"message": "Test message", "severity": "info"},
        )
        self.assertEqual(response.status_code, 403)


class ManageMiddlewareTest(TestCase):
    def test_claim_configuration_health_check(self) -> None:
        with (
            patch("weblate.wladmin.middleware.time.time", return_value=123),
            patch(
                "weblate.wladmin.middleware.cache.add", return_value=True
            ) as cache_add,
        ):
            self.assertTrue(claim_configuration_health_check())

        cache_add.assert_called_once_with(
            CHECK_ATTEMPT_CACHE_KEY,
            123,
            timeout=CHECK_ATTEMPT_TIMEOUT,
        )

    @override_settings(BACKGROUND_ADMIN_CHECKS=False)
    def test_disabled(self) -> None:
        middleware = ManageMiddleware(Mock())
        with patch.object(middleware, "should_poll") as should_poll:
            middleware.trigger_check_if_due()
        should_poll.assert_not_called()

    @override_settings(BACKGROUND_ADMIN_CHECKS=True)
    def test_poll_interval(self) -> None:
        middleware = ManageMiddleware(Mock())
        with (
            patch(
                "weblate.wladmin.middleware.time.monotonic",
                side_effect=[100, 120, 100 + CHECK_POLL_INTERVAL],
            ),
            patch("weblate.wladmin.middleware.cache.get", return_value=None),
            patch.object(middleware, "trigger_check") as trigger_check,
        ):
            middleware.trigger_check_if_due()
            middleware.trigger_check_if_due()
            middleware.trigger_check_if_due()

        self.assertEqual(trigger_check.call_count, 2)

    @override_settings(BACKGROUND_ADMIN_CHECKS=True)
    def test_recent_check(self) -> None:
        middleware = ManageMiddleware(Mock())
        with (
            patch("weblate.wladmin.middleware.time.monotonic", return_value=100),
            patch("weblate.wladmin.middleware.time.time", return_value=1000),
            patch(
                "weblate.wladmin.middleware.cache.get",
                return_value=1000 - CHECK_INTERVAL + 1,
            ),
            patch.object(middleware, "trigger_check") as trigger_check,
        ):
            middleware.trigger_check_if_due()

        trigger_check.assert_not_called()

    @override_settings(BACKGROUND_ADMIN_CHECKS=True)
    def test_atomic_attempt_claim(self) -> None:
        with (
            patch(
                "weblate.wladmin.middleware.claim_configuration_health_check",
                return_value=False,
            ),
            patch("weblate.wladmin.middleware.Thread") as thread,
        ):
            ManageMiddleware.trigger_check()

        thread.assert_not_called()

    @override_settings(BACKGROUND_ADMIN_CHECKS=True)
    def test_starts_background_thread(self) -> None:
        with (
            patch(
                "weblate.wladmin.middleware.claim_configuration_health_check",
                return_value=True,
            ),
            patch("weblate.wladmin.middleware.Thread") as thread,
        ):
            ManageMiddleware.trigger_check()

        thread.assert_called_once_with(
            target=run_background_configuration_health_check,
            name="configuration-health-check",
            daemon=False,
        )
        thread.return_value.start.assert_called_once_with()

    @override_settings(BACKGROUND_ADMIN_CHECKS=True)
    def test_thread_start_failure(self) -> None:
        with (
            patch(
                "weblate.wladmin.middleware.claim_configuration_health_check",
                return_value=True,
            ),
            patch(
                "weblate.wladmin.middleware.Thread",
                side_effect=RuntimeError("thread failed"),
            ),
            patch("weblate.wladmin.middleware.report_error") as report_error,
        ):
            ManageMiddleware.trigger_check()

        report_error.assert_called_once_with(
            "Could not start configuration health check"
        )

    def test_perform_configuration_health_check(self) -> None:
        checks = [Critical(msg="Test error", id="weblate.E002")]
        with (
            patch.object(
                ConfigurationError.objects, "configuration_health_check"
            ) as health_check,
            patch("weblate.wladmin.middleware.time.time", return_value=123),
            patch("weblate.wladmin.middleware.cache.set") as cache_set,
        ):
            self.assertTrue(perform_configuration_health_check(checks))

        health_check.assert_called_once_with(checks)
        cache_set.assert_called_once_with(CHECK_CACHE_KEY, 123, timeout=None)

    def test_perform_configuration_health_check_failure(self) -> None:
        with (
            patch.object(
                ConfigurationError.objects,
                "configuration_health_check",
                side_effect=RuntimeError("check failed"),
            ),
            patch("weblate.wladmin.middleware.cache.set") as cache_set,
            patch("weblate.wladmin.middleware.report_error") as report_error,
        ):
            self.assertFalse(perform_configuration_health_check())

        cache_set.assert_not_called()
        report_error.assert_called_once_with("Configuration health check failed")

    def test_background_check_closes_connections(self) -> None:
        with (
            patch("weblate.wladmin.middleware.perform_configuration_health_check"),
            patch("weblate.wladmin.middleware.connections.close_all") as close_all,
        ):
            run_background_configuration_health_check()

        close_all.assert_called_once_with()

    def test_background_check_closes_connections_on_failure(self) -> None:
        with (
            patch(
                "weblate.wladmin.middleware.perform_configuration_health_check",
                side_effect=RuntimeError("reporting failed"),
            ),
            patch("weblate.wladmin.middleware.connections.close_all") as close_all,
            self.assertRaises(RuntimeError),
        ):
            run_background_configuration_health_check()

        close_all.assert_called_once_with()


class AdminTest(ViewTestCase):
    """Test for customized admin interface."""

    def setUp(self) -> None:
        super().setUp()
        self.user.is_superuser = True
        self.user.save()

    def test_index(self) -> None:
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "SSH")

    @override_settings(SITE_TITLE="Test Weblate")
    def test_manage_index(self) -> None:
        response = self.client.get(reverse("manage"))
        self.assertContains(response, "SSH")
        self.assertContains(response, "Discover Weblate")
        self.assertContains(response, "Enable Discover Weblate")
        self.assertContains(response, reverse("manage-discovery-register"))
        self.assertNotContains(response, "Register on weblate.org")

    def test_manage_index_discovery_registration_requires_site_title(self) -> None:
        response = self.client.get(reverse("manage"))
        self.assertContains(response, "Discover Weblate")
        self.assertContains(response, "Please change SITE_TITLE")
        self.assertNotContains(response, "Enable Discover Weblate")
        self.assertNotContains(response, reverse("manage-discovery-register"))

    @override_settings(SITE_TITLE="Test Weblate")
    def test_manage_index_hides_discovery_registration_for_support(self) -> None:
        SupportStatus.objects.create(
            name="hosted",
            secret="paid-secret",
            expiry=timezone.now(),
            has_subscription=True,
            enabled=True,
        )
        response = self.client.get(reverse("manage"))
        self.assertContains(response, "Discover Weblate")
        self.assertContains(response, "Enable discovery")
        self.assertContains(response, reverse("manage-discovery"))
        self.assertContains(response, "Manage your listing")
        self.assertNotContains(response, "Register on weblate.org")

    @override_settings(SITE_TITLE="Test Weblate")
    def test_manage_index_unlink_mentions_discovery(self) -> None:
        SupportStatus.objects.create(
            name="hosted",
            secret="paid-secret",
            expiry=timezone.now(),
            has_subscription=True,
            enabled=True,
            discoverable=True,
        )

        response = self.client.get(reverse("manage"))

        self.assertContains(
            response, "Unlink support package and disable Discover Weblate"
        )

    def test_backup_page_hides_discovery_registration(self) -> None:
        response = self.client.get(reverse("manage-backups"))
        self.assertNotContains(response, "Register on weblate.org")

    def test_workspaces(self) -> None:
        workspace = Workspace.objects.create(name="Test workspace")
        Project.objects.create(
            name="Workspace project",
            slug="workspace-project",
            web="https://example.com/",
            workspace=workspace,
        )

        response = self.client.get(reverse("manage-workspaces"))

        self.assertContains(response, "Manage workspaces")
        self.assertContains(response, workspace.name)
        self.assertContains(response, workspace.get_absolute_url())
        self.assertContains(response, ">1<")
        self.assertContains(response, "table-striped")
        self.assertContains(response, "Translated")
        self.assertContains(response, "Unfinished words")

    def test_workspaces_stats_sort_preserves_search(self) -> None:
        workspaces = Workspace.objects.bulk_create(
            [
                Workspace(name=f"Sortable localization workspace {index:02}")
                for index in range(51)
            ]
        )
        Workspace.objects.create(name="Unrelated documentation workspace")

        response = self.client.get(
            reverse("manage-workspaces"),
            {"q": "localization", "sort_by": "translated"},
        )

        self.assertEqual(len(response.context["object_list"]), 50)
        self.assertEqual(
            set(response.context["object_list"]),
            set(workspaces[:50]),
        )
        self.assertContains(response, "sort_by=-translated&amp;q=localization")
        self.assertEqual(
            response.context["object_list"].paginator.sort_by,
            "translated",
        )

    def test_alerts_are_ordered(self) -> None:
        zulu_project = self.create_project(name="Zulu", slug="zulu")
        zulu = self.create_json(project=zulu_project, name="Zulu")
        alpha_project = self.create_project(name="Alpha", slug="alpha")
        alpha = self.create_json(project=alpha_project, name="Alpha")

        zulu.add_alert("MissingLicense")
        alpha.add_alert("MissingLicense")

        response = self.client.get(reverse("manage-alerts"))
        content = response.content.decode()

        self.assertContains(response, alpha.get_absolute_url())
        self.assertContains(response, zulu.get_absolute_url())
        self.assertLess(
            content.index(alpha.get_absolute_url()),
            content.index(zulu.get_absolute_url()),
        )

    def test_workspaces_search(self) -> None:
        workspace = Workspace.objects.create(name="Localization workspace")
        Workspace.objects.create(name="Documentation workspace")

        response = self.client.get(reverse("manage-workspaces"), {"q": "local"})

        self.assertContains(response, "Localization workspace")
        self.assertNotContains(response, "Documentation workspace")
        self.assertEqual(list(response.context["object_list"]), [workspace])
        self.assertEqual(response.context["search_query"], "local")
        self.assertEqual(response.context["query_string"], "q=local")

        response = self.client.get(reverse("manage-workspaces"), {"q": "missing"})

        self.assertContains(response, "No workspaces found.")
        self.assertNotContains(response, "Localization workspace")
        self.assertNotContains(response, "Documentation workspace")

    def test_workspaces_search_billing_customer_name(self) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.billing.models import Billing, Plan

        plan = Plan.objects.create(
            name="Workspace plan",
            price=19,
            yearly_price=199,
            limit_projects=1,
            display_limit_projects=1,
        )
        billing = Billing.objects.create(plan=plan, customer_name="Acme Billing LLC")
        workspace = billing.workspace
        workspace.name = "Manually renamed workspace"
        workspace.save(update_fields=["name"])
        Workspace.objects.create(name="Acme localization workspace")

        response = self.client.get(reverse("manage-workspaces"), {"q": "billing"})

        self.assertContains(response, "Manually renamed workspace")
        self.assertContains(response, "Acme Billing LLC")
        self.assertNotContains(response, "Acme localization workspace")
        self.assertEqual(list(response.context["object_list"]), [workspace])

    @modify_settings(INSTALLED_APPS={"remove": "weblate.billing"})
    def test_workspaces_add_link(self) -> None:
        response = self.client.get(reverse("manage-workspaces"))

        self.assertContains(response, reverse("manage-workspace-add"))
        self.assertContains(response, "Add workspace")

    def test_workspaces_add_link_hidden_with_billing(self) -> None:
        response = self.client.get(reverse("manage-workspaces"))

        self.assertNotContains(response, reverse("manage-workspace-add"))
        self.assertNotContains(response, "Add workspace")

    def test_workspace_add_hidden_from_sitewide_menu_with_billing(self) -> None:
        response = self.client.get(reverse("home"))

        self.assertNotContains(response, "Add new workspace")

    def test_workspace_add_direct_access_hidden_with_billing(self) -> None:
        response = self.client.get(reverse("manage-workspace-add"))

        self.assertEqual(response.status_code, 404)

    def test_workspaces_pagination(self) -> None:
        for index in range(51):
            Workspace.objects.create(name=f"Workspace {index:02}")

        response = self.client.get(reverse("manage-workspaces"))

        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(len(response.context["object_list"]), 50)

    def test_workspaces_batch_project_stats_queries(self) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.billing.models import Billing, Plan

        plan = Plan.objects.create(
            name="Workspace plan",
            price=19,
            yearly_price=199,
            limit_projects=1,
            display_limit_projects=1,
        )

        for index in range(3):
            billing = Billing.objects.create(plan=plan)
            project = Project.objects.create(
                name=f"Billed project {index}",
                slug=f"billed-project-{index}",
                web="https://example.com/",
            )
            billing.add_project(project)

        # ruff: ignore[private-member-access]
        project_table = Project._meta.db_table
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("manage-workspaces"))

        self.assertContains(response, "Billing #")
        project_queries = [
            query["sql"]
            for query in queries
            if (
                f'FROM "{project_table}"' in query["sql"]
                and f'WHERE "{project_table}"."workspace_id"' in query["sql"]
            )
        ]
        self.assertEqual(len(project_queries), 1)
        self.assertIn('"workspace_id" IN', project_queries[0])

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
        with restored_environment("PATH", oldpath):
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

        # Check the file contains it
        self.assertIn("example.com", hostsfile.read_text())

    @tempdir_setting("BACKUP_DIR")
    def test_backup(self) -> None:
        def do_post(**payload):
            return self.client.post(reverse("manage-backups"), payload, follow=True)

        response = do_post(repository=settings.BACKUP_DIR)
        self.assertContains(response, settings.BACKUP_DIR)
        service = BackupService.objects.get()
        self.assertContains(response, 'class="naturaltime"', count=1)
        service.backuplog_set.create(event="backup", log="borg backup output")
        response = self.client.get(reverse("manage-backups"))
        self.assertContains(response, 'class="naturaltime"', count=2)
        response = do_post(service=service.pk, trigger="1")
        self.assertContains(response, "triggered")
        response = do_post(service=service.pk, toggle="1")
        self.assertContains(response, "Turned off")
        response = do_post(service=service.pk, remove="1")
        self.assertNotContains(response, settings.BACKUP_DIR)

    def test_performance(self) -> None:
        with (
            patch("weblate.wladmin.views.get_database_size", return_value=123456789),
            patch(
                "weblate.wladmin.views.get_database_disk_usage",
                return_value=SimpleNamespace(total=987654321, free=876543210),
            ),
        ):
            response = self.client.get(reverse("manage-performance"))
        self.assertContains(response, "weblate.E005")
        self.assertContains(response, "Translation memory migration")
        self.assertContains(response, "PostgreSQL database")
        self.assertEqual(response.context["database_size"], 123456789)
        self.assertEqual(response.context["database_disk_usage"].free, 876543210)
        self.assertIn("total", response.context["memory_migration_status"])

    def test_performance_memory_migration_status(self) -> None:
        Memory.objects.all().delete()
        MemoryScopeMigrationState.objects.all().delete()
        memory = Memory.objects.create(
            source="Hello",
            target="Ahoj",
            origin="project/component",
            source_language_id=1,
            target_language_id=2,
        )
        Memory.objects.create(
            source=memory.source,
            target=memory.target,
            origin=memory.origin,
            source_language_id=memory.source_language_id,
            target_language_id=memory.target_language_id,
        )
        MemoryScopeMigrationState.objects.create(
            name="memory-scope-backfill", last_memory_id=memory.id
        )

        response = self.client.get(reverse("manage-performance"))

        self.assertContains(response, "Backfilling scopes")
        status = response.context["memory_migration_status"]
        first_memory = Memory.objects.order_by("-id").first()
        assert first_memory is not None
        self.assertEqual(status["total"], first_memory.id)
        self.assertEqual(status["processed"], memory.id)
        self.assertFalse(response.context["memory_migration_status"]["completed"])

    def test_performance_memory_migration_status_without_state(self) -> None:
        Memory.objects.all().delete()
        MemoryScopeMigrationState.objects.all().delete()
        memory = Memory.objects.create(
            source="Hello",
            target="Ahoj",
            origin="project/component",
            source_language_id=1,
            target_language_id=2,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_GLOBAL_FILE,
        )

        response = self.client.get(reverse("manage-performance"))

        self.assertContains(response, "Not yet started")
        self.assertContains(response, "Scanning duplicate candidates")
        status = response.context["memory_migration_status"]
        self.assertEqual(status["processed"], memory.id)
        self.assertFalse(status["completed"])
        self.assertTrue(status["compaction_active"])

    def test_performance_memory_migration_status_with_duplicates(self) -> None:
        Memory.objects.all().delete()
        MemoryScopeMigrationState.objects.all().delete()
        memory = Memory.objects.create(
            source="Hello",
            target="Ahoj",
            origin="project/component",
            source_language_id=1,
            target_language_id=2,
        )
        Memory.objects.create(
            source=memory.source,
            target=memory.target,
            origin=memory.origin,
            source_language_id=memory.source_language_id,
            target_language_id=memory.target_language_id,
        )
        MemoryScopeMigrationState.objects.create(
            name="memory-scope-backfill", last_memory_id=memory.id, completed=True
        )

        response = self.client.get(reverse("manage-performance"))

        self.assertContains(response, "Scanning duplicate candidates")
        self.assertNotContains(response, "Candidate duplicate buckets")
        self.assertContains(response, "Duplicate candidate scan")
        self.assertNotContains(response, "Not calculated during active scan")
        self.assertNotContains(response, "Duplicate groups pending consolidation")
        self.assertFalse(response.context["memory_migration_status"]["completed"])
        self.assertEqual(
            response.context["memory_migration_status"]["compaction_last_memory_id"], 0
        )
        self.assertEqual(
            response.context["memory_migration_status"]["compaction_max_memory_id"],
            Memory.objects.order_by("-id").values_list("id", flat=True).first(),
        )
        self.assertEqual(
            response.context["memory_migration_status"]["compaction_percent"], 0
        )

    def test_performance_memory_migration_status_with_compaction_progress(
        self,
    ) -> None:
        Memory.objects.all().delete()
        MemoryScopeMigrationState.objects.all().delete()
        first = Memory.objects.create(
            source="Hello",
            target="Ahoj",
            origin="project/component",
            source_language_id=1,
            target_language_id=2,
        )
        Memory.objects.create(
            source=first.source,
            target=first.target,
            origin=first.origin,
            source_language_id=first.source_language_id,
            target_language_id=first.target_language_id,
        )
        MemoryScopeMigrationState.objects.create(
            name="memory-scope-backfill", last_memory_id=first.id, completed=True
        )
        MemoryScopeMigrationState.objects.create(
            name="memory-scope-compaction", last_memory_id=first.id
        )

        response = self.client.get(reverse("manage-performance"))

        status = response.context["memory_migration_status"]
        self.assertContains(response, "Scanning duplicate candidates")
        self.assertTrue(status["compaction_active"])
        self.assertFalse(status["compaction_completed"])
        self.assertEqual(status["compaction_last_memory_id"], first.id)
        self.assertGreater(status["compaction_percent"], 0)
        self.assertLessEqual(status["compaction_percent"], 100)

    def test_performance_memory_migration_status_completed_compaction(self) -> None:
        Memory.objects.all().delete()
        MemoryScopeMigrationState.objects.all().delete()
        memory = Memory.objects.create(
            source="Hello",
            target="Ahoj",
            origin="project/component",
            source_language_id=1,
            target_language_id=2,
        )
        Memory.objects.create(
            source=memory.source,
            target=memory.target,
            origin=memory.origin,
            source_language_id=memory.source_language_id,
            target_language_id=memory.target_language_id,
        )
        MemoryScopeMigrationState.objects.create(
            name="memory-scope-backfill", last_memory_id=memory.id, completed=True
        )
        MemoryScopeMigrationState.objects.create(
            name="memory-scope-compaction",
            last_memory_id=memory.id,
            completed=True,
        )

        response = self.client.get(reverse("manage-performance"))

        status = response.context["memory_migration_status"]
        self.assertContains(response, "Completed")
        self.assertTrue(status["completed"])
        self.assertTrue(status["compaction_completed"])
        self.assertFalse(status["compaction_active"])
        self.assertEqual(status["compaction_percent"], 100)

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

    @override_settings(BACKGROUND_ADMIN_CHECKS=True)
    def test_performance_persists_existing_checks(self) -> None:
        checks = [Critical(msg="Test Error", id="weblate.E002")]
        with (
            patch("weblate.wladmin.views.run_checks", return_value=checks),
            patch(
                "weblate.wladmin.views.claim_configuration_health_check",
                return_value=True,
            ) as claim_health_check,
            patch(
                "weblate.wladmin.views.perform_configuration_health_check"
            ) as perform_health_check,
            patch(
                "weblate.wladmin.middleware.ManageMiddleware.should_poll",
                return_value=False,
            ),
        ):
            response = self.client.get(reverse("manage-performance"))

        self.assertEqual(response.status_code, 200)
        claim_health_check.assert_called_once_with()
        perform_health_check.assert_called_once_with(checks)

    @override_settings(BACKGROUND_ADMIN_CHECKS=True)
    def test_performance_skips_persistence_during_active_check(self) -> None:
        checks = [Critical(msg="Test Error", id="weblate.E002")]
        with (
            patch("weblate.wladmin.views.run_checks", return_value=checks),
            patch(
                "weblate.wladmin.views.claim_configuration_health_check",
                return_value=False,
            ),
            patch(
                "weblate.wladmin.views.perform_configuration_health_check"
            ) as perform_health_check,
            patch(
                "weblate.wladmin.middleware.ManageMiddleware.should_poll",
                return_value=False,
            ),
        ):
            response = self.client.get(reverse("manage-performance"))

        self.assertEqual(response.status_code, 200)
        perform_health_check.assert_not_called()

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
                Critical(msg="Cache Error", id="weblate.C044"),
                Critical(msg="Database statistics error", id="weblate.C047"),
            ]
        )
        all_errors = ConfigurationError.objects.all()
        self.assertEqual(len(all_errors), 3)
        self.assertEqual(
            {error.name: error.message for error in all_errors},
            {
                "weblate.E002": "Test Error",
                "weblate.C044": "Cache Error",
                "weblate.C047": "Database statistics error",
            },
        )
        # No triggered checks
        ConfigurationError.objects.create(name="weblate.C046", message="Retired check")
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

    def test_manage_users_workspace_teams_avoid_workspace_fetches(self) -> None:
        workspace = Workspace.objects.create(name="User management workspace")
        groups = [
            Group.objects.create(
                name=f"User management workspace team {index}",
                defining_workspace=workspace,
            )
            for index in range(3)
        ]
        for index, group in enumerate(groups):
            Invitation.objects.create(
                author=self.user,
                group=group,
                email=f"workspace-invite-{index}@example.com",
            )

        # ruff: ignore[private-member-access]
        workspace_table = Workspace._meta.db_table
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("manage-users"))

        self.assertContains(response, "User management workspace team 0")
        workspace_fetches = [
            query["sql"]
            for query in queries
            if (
                f'FROM "{workspace_table}"' in query["sql"]
                and f'WHERE "{workspace_table}"."id"' in query["sql"]
            )
        ]
        self.assertEqual(workspace_fetches, [])

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
        email = cast("str", self.user.email)
        response = self.client.get(
            reverse("manage-users-check"), {"q": email}, follow=True
        )
        self.assertRedirects(response, self.user.get_absolute_url())
        response = self.client.get(
            reverse("manage-users-check"), {"email": email}, follow=True
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
            get_support_url(),
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
            get_support_url(),
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
            get_support_url(),
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

    def test_discovery_toggle_requires_site_title(self) -> None:
        status = SupportStatus.objects.create(
            name="community",
            secret="discovery-secret",
            expiry=timezone.now(),
            enabled=True,
        )

        response = self.client.post(reverse("manage-discovery"), follow=True)

        self.assertContains(response, "Please change SITE_TITLE")
        status.refresh_from_db()
        self.assertFalse(status.discoverable)

    @override_settings(
        ENABLE_HTTPS=True,
        SITE_DOMAIN="instance.example",
        SITE_TITLE="Test Weblate",
        SUPPORT_API_URL="https://weblate.example/",
    )
    def test_discovery_registration_redirect(self) -> None:
        response = self.client.post(reverse("manage-discovery-register"))
        self.assertEqual(response.status_code, 302)
        location = urlparse(response["Location"])
        self.assertEqual(
            f"{location.scheme}://{location.netloc}{location.path}",
            "https://weblate.example/subscription/discovery/register/",
        )
        query = parse_qs(location.query)
        self.assertEqual(query["site_url"], ["https://instance.example"])
        self.assertNotIn("callback_url", query)
        self.assertEqual(
            self.client.session[DISCOVERY_REGISTRATION_SESSION]["state"],
            query["state"][0],
        )

    @override_settings(
        ENABLE_HTTPS=True,
        SITE_DOMAIN="instance.example",
        SUPPORT_API_URL="https://weblate.example/",
    )
    def test_discovery_registration_requires_site_title(self) -> None:
        response = self.client.post(reverse("manage-discovery-register"), follow=True)

        self.assertContains(response, "Please change SITE_TITLE")
        self.assertNotIn(DISCOVERY_REGISTRATION_SESSION, self.client.session)

    @override_settings(
        ENABLE_HTTPS=True,
        SITE_DOMAIN="instance.example",
        SUPPORT_API_URL="https://weblate.example/",
    )
    def test_discovery_registration_rejects_existing_link(self) -> None:
        SupportStatus.objects.create(
            name="community",
            secret="discovery-secret",
            expiry=timezone.now(),
            enabled=True,
        )

        response = self.client.post(reverse("manage-discovery-register"), follow=True)

        self.assertContains(response, "already linked to weblate.org")
        self.assertNotIn(DISCOVERY_REGISTRATION_SESSION, self.client.session)

    @override_settings(ENABLE_HTTPS=True, SITE_DOMAIN="instance.example")
    def test_discovery_site_url_uses_callback_prefix(self) -> None:
        self.assertEqual(
            get_discovery_site_url("/translations/manage/discovery/callback/"),
            "https://instance.example/translations",
        )

    @override_settings(SUPPORT_API_URL="https://weblate.example/")
    def test_support_url_from_base(self) -> None:
        self.assertEqual(get_support_url(), "https://weblate.example/api/support/")
        self.assertEqual(
            get_support_url("subscription/discovery/register/"),
            "https://weblate.example/subscription/discovery/register/",
        )

    @override_settings(SUPPORT_API_URL="https://weblate.example/base/")
    def test_support_url_from_base_path(self) -> None:
        self.assertEqual(get_support_url(), "https://weblate.example/base/api/support/")
        self.assertEqual(
            get_support_url("subscription/discovery/register/"),
            "https://weblate.example/base/subscription/discovery/register/",
        )

    def test_discovery_callback_rejects_invalid_state(self) -> None:
        response = self.client.get(
            reverse("manage-discovery-callback"),
            {"code": "code-123", "state": "wrong"},
            follow=True,
        )
        self.assertContains(response, "Invalid activation state.")
        self.assertFalse(SupportStatus.objects.exists())

    @responses.activate
    @override_settings(
        ENABLE_HTTPS=True,
        SITE_DOMAIN="instance.example",
        SITE_TITLE="Test Weblate",
        SUPPORT_API_URL="https://weblate.example/",
    )
    def test_discovery_callback_keeps_state_on_mismatch(self) -> None:
        response = self.client.post(reverse("manage-discovery-register"))
        state = parse_qs(urlparse(response["Location"]).query)["state"][0]

        response = self.client.get(
            reverse("manage-discovery-callback"),
            {"code": "old-code", "state": "stale"},
            follow=True,
        )
        self.assertContains(response, "Invalid activation state.")
        self.assertEqual(
            self.client.session[DISCOVERY_REGISTRATION_SESSION]["state"], state
        )
        self.assertFalse(SupportStatus.objects.exists())

        responses.add(
            responses.POST,
            "https://weblate.example/api/support/activation/",
            json={"secret": "secret-123"},
        )
        responses.add(
            responses.POST,
            get_support_url(),
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

        response = self.client.get(
            reverse("manage-discovery-callback"),
            {"code": "code-123", "state": state},
            follow=True,
        )
        self.assertContains(response, "Activation completed.")
        self.assertEqual(SupportStatus.objects.get().secret, "secret-123")

    @override_settings(
        ENABLE_HTTPS=True,
        SITE_DOMAIN="instance.example",
        SITE_TITLE="Test Weblate",
        SUPPORT_API_URL="https://weblate.example/",
    )
    def test_discovery_callback_rejects_missing_code(self) -> None:
        response = self.client.post(reverse("manage-discovery-register"))
        state = parse_qs(urlparse(response["Location"]).query)["state"][0]

        response = self.client.get(
            reverse("manage-discovery-callback"), {"state": state}, follow=True
        )
        self.assertContains(response, "Missing activation code.")
        self.assertFalse(SupportStatus.objects.exists())

    @responses.activate
    @override_settings(
        ENABLE_HTTPS=True,
        SITE_DOMAIN="instance.example",
        SITE_TITLE="Test Weblate",
        SUPPORT_API_URL="https://weblate.example/",
    )
    def test_discovery_callback_exchanges_code(self) -> None:
        response = self.client.post(reverse("manage-discovery-register"))
        state = parse_qs(urlparse(response["Location"]).query)["state"][0]
        responses.add(
            responses.POST,
            "https://weblate.example/api/support/activation/",
            json={"secret": "secret-123"},
        )
        responses.add(
            responses.POST,
            get_support_url(),
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

        with (
            patch(
                "weblate.wladmin.views.get_discovery_site_url",
                return_value="https://instance.example/translations",
            ),
            patch("weblate.wladmin.views.support_status_update.delay") as update_task,
            self.captureOnCommitCallbacks(execute=False) as callbacks,
        ):
            response = self.client.get(
                reverse("manage-discovery-callback"),
                {"code": "code-123", "state": state},
                follow=True,
            )
        update_task.assert_not_called()
        self.assertGreaterEqual(len(callbacks), 1)
        for callback in callbacks:
            callback()
        update_task.assert_called_once_with()
        self.assertContains(response, "Activation completed.")
        status = SupportStatus.objects.get()
        self.assertEqual(status.secret, "secret-123")
        self.assertEqual(status.name, "community")
        self.assertTrue(status.discoverable)
        self.assertEqual(get_response_call_body(0), "code=code-123")
        refresh_body = parse_qs(get_response_call_body(1))
        self.assertEqual(
            refresh_body["site_url"], ["https://instance.example/translations"]
        )
        self.assertNotIn("discoverable", refresh_body)
        self.assertNotIn("public_projects", refresh_body)

    @responses.activate
    def test_support_refresh_includes_discoverable_projects(self) -> None:
        Project.objects.update(access_control=Project.ACCESS_PRIVATE)
        Project.objects.create(
            name="Public project",
            slug="public-project",
            web="https://public.example/",
            access_control=Project.ACCESS_PUBLIC,
        )
        Project.objects.create(
            name="Protected project",
            slug="protected-project",
            web="https://protected.example/",
            access_control=Project.ACCESS_PROTECTED,
        )
        Project.objects.create(
            name="Private project",
            slug="private-project",
            web="https://private.example/",
            access_control=Project.ACCESS_PRIVATE,
        )
        responses.add(
            responses.POST,
            get_support_url(),
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

        SupportStatus(secret="secret-123", discoverable=True).refresh()

        refresh_body = parse_qs(get_response_call_body(0))
        self.assertEqual(refresh_body["discoverable"], ["1"])
        discover_projects = json.loads(refresh_body["public_projects"][0])
        self.assertEqual(
            {project["name"] for project in discover_projects},
            {"Public project", "Protected project"},
        )

    @override_settings(
        ENABLE_HTTPS=True,
        SITE_DOMAIN="instance.example",
        SITE_TITLE="Test Weblate",
        SUPPORT_API_URL="https://weblate.example/",
    )
    def test_discovery_callback_rejects_long_code(self) -> None:
        response = self.client.post(reverse("manage-discovery-register"))
        state = parse_qs(urlparse(response["Location"]).query)["state"][0]

        response = self.client.get(
            reverse("manage-discovery-callback"),
            {"code": "x" * 101, "state": state},
            follow=True,
        )
        self.assertContains(response, "Invalid activation code.")
        self.assertFalse(SupportStatus.objects.exists())

    @override_settings(
        ENABLE_HTTPS=True,
        SITE_DOMAIN="instance.example",
        SITE_TITLE="Test Weblate",
        SUPPORT_API_URL="https://weblate.example/",
    )
    def test_discovery_callback_hides_exchange_error(self) -> None:
        response = self.client.post(reverse("manage-discovery-register"))
        state = parse_qs(urlparse(response["Location"]).query)["state"][0]

        with patch(
            "weblate.wladmin.views.fetch_url",
            side_effect=RuntimeError("internal detail"),
        ):
            response = self.client.get(
                reverse("manage-discovery-callback"),
                {"code": "code-123", "state": state},
                follow=True,
            )
        self.assertContains(response, "Please try again later.")
        self.assertNotContains(response, "internal detail")
        self.assertFalse(SupportStatus.objects.exists())

    @responses.activate
    @override_settings(
        ENABLE_HTTPS=True,
        SITE_DOMAIN="instance.example",
        SUPPORT_API_URL="https://weblate.example/",
    )
    def test_discovery_callback_exchange_error_keeps_existing_status(self) -> None:
        old_status = SupportStatus.objects.create(
            name="community",
            secret="old-secret",
            expiry=timezone.now(),
            enabled=True,
        )
        session = self.client.session
        session[DISCOVERY_REGISTRATION_SESSION] = {
            "state": "state-123",
            "expires": (timezone.now() + DISCOVERY_REGISTRATION_STATE_AGE).timestamp(),
        }
        session.save()
        responses.add(
            responses.POST,
            "https://weblate.example/api/support/activation/",
            status=500,
        )

        response = self.client.get(
            reverse("manage-discovery-callback"),
            {"code": "code-123", "state": "state-123"},
            follow=True,
        )
        self.assertContains(response, "Please try again later.")
        old_status.refresh_from_db()
        self.assertTrue(old_status.enabled)
        self.assertEqual(SupportStatus.objects.get_current(), old_status)

    @responses.activate
    @override_settings(
        ENABLE_HTTPS=True,
        SITE_DOMAIN="instance.example",
        SITE_TITLE="Test Weblate",
        SUPPORT_API_URL="https://weblate.example/",
    )
    def test_discovery_callback_preserves_subscription(self) -> None:
        old_status = SupportStatus.objects.create(
            name="hosted",
            secret="paid-secret",
            expiry=timezone.now(),
            has_subscription=True,
            enabled=True,
        )
        session = self.client.session
        session[DISCOVERY_REGISTRATION_SESSION] = {
            "state": "state-123",
            "expires": (timezone.now() + DISCOVERY_REGISTRATION_STATE_AGE).timestamp(),
        }
        session.save()
        responses.add(
            responses.POST,
            "https://weblate.example/api/support/activation/",
            json={"secret": "discovery-secret"},
        )
        responses.add(
            responses.POST,
            get_support_url(),
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

        response = self.client.get(
            reverse("manage-discovery-callback"),
            {"code": "code-123", "state": "state-123"},
            follow=True,
        )

        self.assertContains(response, "a support package is already linked")
        refresh_body = parse_qs(get_response_call_body(1))
        self.assertNotIn("discoverable", refresh_body)
        self.assertNotIn("public_projects", refresh_body)
        old_status.refresh_from_db()
        self.assertTrue(old_status.enabled)
        self.assertEqual(SupportStatus.objects.get_current(), old_status)
        self.assertFalse(
            SupportStatus.objects.filter(secret="discovery-secret").exists()
        )

    @responses.activate
    def test_activation_unlink_disables_discovery_remotely(self) -> None:
        SupportStatus.objects.create(
            name="community",
            secret="discovery-secret",
            expiry=timezone.now(),
            discoverable=True,
            enabled=True,
        )
        responses.add(
            responses.POST,
            get_support_url(),
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

        self.client.post(reverse("manage-activate"), {"unlink": "1"})

        unlink_body = parse_qs(get_response_call_body(0))
        self.assertEqual(unlink_body["secret"], ["discovery-secret"])
        self.assertNotIn("discoverable", unlink_body)
        self.assertNotIn("public_projects", unlink_body)
        self.assertFalse(SupportStatus.objects.filter(enabled=True).exists())

    @responses.activate
    def test_activation_unlink_disables_locally_on_discovery_error(self) -> None:
        status = SupportStatus.objects.create(
            name="community",
            secret="discovery-secret",
            expiry=timezone.now(),
            discoverable=True,
            enabled=True,
        )
        responses.add(
            responses.POST,
            get_support_url(),
            status=500,
        )

        response = self.client.post(
            reverse("manage-activate"), {"unlink": "1"}, follow=True
        )

        self.assertContains(response, "unlinked locally")
        self.assertFalse(SupportStatus.objects.filter(enabled=True).exists())
        status.refresh_from_db()
        self.assertFalse(status.enabled)
        self.assertFalse(status.discoverable)

    @responses.activate
    @override_settings(SITE_TITLE="Test Weblate")
    def test_activation_hosted(self) -> None:
        with TemporaryDirectory() as tempdir:
            responses.add(
                responses.POST,
                get_support_url(),
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
            responses.delete(responses.POST, get_support_url())
            responses.add(
                responses.POST,
                get_support_url(),
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
