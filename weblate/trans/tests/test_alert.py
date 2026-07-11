# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for alerts."""

import importlib
import os
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from weblate.addons.gettext import MsgmergeAddon, SphinxAddon, XgettextAddon
from weblate.addons.models import Addon
from weblate.auth.models import Group, Permission, Role
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.alerts.base import AlertSeverity
from weblate.trans.alerts.registry import update_alerts
from weblate.trans.alerts.vcs import UpdateFailure
from weblate.trans.models import Component, Project, Unit
from weblate.trans.tests.test_views import ViewTestCase
from weblate.vcs.models import VCS_REGISTRY

if TYPE_CHECKING:
    from weblate.trans.models.alert import Alert


class WebsiteAlertSettingTest(ViewTestCase):
    """Test WEBSITE_ALERTS_ENABLED setting."""

    def create_component(self):
        return self._create_component("po", "po/*.po")

    @override_settings(WEBSITE_ALERTS_ENABLED=False)
    @patch("weblate.trans.alerts.config.get_uri_error", return_value="unreachable")
    def test_website_alerts_disabled(self, mocked_get_uri_error) -> None:
        """Test that website alerts are not created when setting is False."""
        self.project.web = "https://example.com/project"
        update_alerts(self.component, {"BrokenProjectURL"})
        self.assertFalse(
            self.component.alert_set.filter(name="BrokenProjectURL").exists()
        )
        mocked_get_uri_error.assert_not_called()

    @override_settings(WEBSITE_ALERTS_ENABLED=True)
    @patch("weblate.trans.alerts.config.get_uri_error", return_value="unreachable")
    def test_website_alerts_enabled(self, mocked_get_uri_error) -> None:
        """Test that website alerts are created when setting is True."""
        self.project.web = "https://example.com/project"
        update_alerts(self.component, {"BrokenProjectURL"})
        self.assertTrue(
            self.component.alert_set.filter(name="BrokenProjectURL").exists()
        )
        mocked_get_uri_error.assert_called_once_with(
            "https://example.com/project", allow_private_targets=False
        )

    @override_settings(WEBSITE_ALERTS_ENABLED=True)
    @patch("weblate.trans.alerts.config.get_uri_error")
    def test_website_alert_uses_validator_error_without_fetch(
        self, mocked_get_uri_error
    ) -> None:
        self.project.web = "https://localhost/project"

        update_alerts(self.component, {"BrokenProjectURL"})

        self.assertTrue(
            self.component.alert_set.filter(name="BrokenProjectURL").exists()
        )
        self.assertEqual(
            self.component.alert_set.get(name="BrokenProjectURL").details["error"],
            "This URL is prohibited because it uses a restricted host.",
        )
        mocked_get_uri_error.assert_not_called()

    @override_settings(WEBSITE_ALERTS_ENABLED=True)
    @patch(
        "weblate.trans.alerts.config.validate_request_url",
        side_effect=ValidationError("URL domain is not allowed."),
    )
    @patch("weblate.trans.alerts.config.get_uri_error")
    def test_website_alert_uses_runtime_validation_without_fetch(
        self, mocked_get_uri_error, mocked_validate_request_url
    ) -> None:
        self.project.web = "https://public.example/project"

        update_alerts(self.component, {"BrokenProjectURL"})

        self.assertTrue(
            self.component.alert_set.filter(name="BrokenProjectURL").exists()
        )
        self.assertEqual(
            self.component.alert_set.get(name="BrokenProjectURL").details["error"],
            "URL domain is not allowed.",
        )
        mocked_validate_request_url.assert_called_once_with(
            "https://public.example/project", allow_private_targets=False
        )
        mocked_get_uri_error.assert_not_called()

    @override_settings(
        WEBSITE_ALERTS_ENABLED=True,
        PROJECT_WEB_RESTRICT_ALLOWLIST={"test"},
    )
    @patch("weblate.trans.alerts.config.get_uri_error", return_value=None)
    @patch("weblate.trans.alerts.config.validate_request_url")
    def test_website_alert_respects_project_allowlist(
        self, mocked_validate_request_url, mocked_get_uri_error
    ) -> None:
        self.project.web = "https://localhost/project"

        update_alerts(self.component, {"BrokenProjectURL"})

        self.assertFalse(
            self.component.alert_set.filter(name="BrokenProjectURL").exists()
        )
        mocked_validate_request_url.assert_called_once_with(
            "https://localhost/project", allow_private_targets=True
        )
        mocked_get_uri_error.assert_called_once_with(
            "https://localhost/project", allow_private_targets=True
        )


class AlertTest(ViewTestCase):
    def create_component(self):
        return self._create_component("po", "po-duplicates/*.dpo", manage_units=True)

    def update_component_alerts(self, component: Component | None = None) -> Component:
        component = Component.objects.get(pk=(component or self.component).pk)
        with self.captureOnCommitCallbacks(execute=True):
            component.update_alerts()
        return component

    def get_problem_alert_names(self) -> set[str]:
        self.update_component_alerts()
        return set(
            self.component.alert_set.filter(
                severity__gte=AlertSeverity.ERROR
            ).values_list("name", flat=True)
        )

    def test_duplicates(self) -> None:
        self.assertEqual(
            self.get_problem_alert_names(),
            {
                "DuplicateLanguage",
                "DuplicateString",
                "BrokenBrowserURL",
                "BrokenProjectURL",
            },
        )
        alert = self.component.alert_set.get(name="DuplicateLanguage")
        self.assertEqual(alert.details["occurrences"][0]["language_code"], "cs")
        alert = self.component.alert_set.get(name="DuplicateString")
        occurrences = alert.details["occurrences"]
        self.assertEqual(len(occurrences), 1)
        self.assertEqual(occurrences[0]["source"], "Thank you for using Weblate.")
        # There should be single unit
        unit = Unit.objects.filter(
            pk__in={item["unit_pk"] for item in occurrences}
        ).get()
        # Remove the unit
        with self.captureOnCommitCallbacks(execute=True):
            unit.translation.delete_unit(None, unit)

        # The alert should have been removed now
        self.assertEqual(
            self.get_problem_alert_names(),
            {
                "DuplicateLanguage",
                "BrokenBrowserURL",
                "BrokenProjectURL",
            },
        )

    def test_unused_enforced(self) -> None:
        self.assertEqual(
            self.get_problem_alert_names(),
            {
                "DuplicateLanguage",
                "DuplicateString",
                "BrokenBrowserURL",
                "BrokenProjectURL",
            },
        )
        self.component.enforced_checks = ["es_format"]
        with self.captureOnCommitCallbacks(execute=True):
            self.component.save()
        self.assertEqual(
            self.get_problem_alert_names(),
            {
                "DuplicateLanguage",
                "DuplicateString",
                "BrokenBrowserURL",
                "BrokenProjectURL",
                "UnusedEnforcedCheck",
            },
        )

    def test_dismiss(self) -> None:
        self.update_component_alerts()
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("dismiss-alert", kwargs=self.kw_component),
            {"dismiss": "BrokenBrowserURL", "reason": "Expected authentication"},
        )
        self.assertRedirects(response, f"{self.component.get_absolute_url()}#alerts")
        alert = self.component.alert_set.get(name="BrokenBrowserURL")
        self.assertIsNotNone(alert.dismissed_at)
        self.assertEqual(alert.dismissed_by, self.user)
        self.assertEqual(alert.dismissal_reason, "Expected authentication")
        self.assertTrue(
            self.component.change_set.filter(
                action=ActionEvents.ALERT_DISMISSED, alert=alert, user=self.user
            ).exists()
        )
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Expected authentication")

        self.client.logout()
        response = self.client.get(self.component.get_absolute_url())
        self.assertNotContains(response, "Expected authentication")

    def test_project_maintainer_can_dismiss_project_wide_alert(self) -> None:
        role = Role.objects.create(name="Project alert maintainer")
        role.permissions.add(Permission.objects.get(codename="project.edit"))
        group = Group.objects.create(name="Project alert maintainers")
        group.roles.add(role)
        group.projects.add(self.component.project)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.assertTrue(self.user.has_perm("project.edit", self.component.project))
        self.assertFalse(self.user.has_perm("component.edit", self.component))
        self.component.add_alert("BrokenProjectURL", error="failure")

        response = self.client.get(f"{self.component.get_absolute_url()}?alerts=1")
        self.assertContains(response, "Optional dismissal reason")
        response = self.client.post(
            reverse("dismiss-alert", kwargs=self.kw_component),
            {"dismiss": "BrokenProjectURL", "reason": "Expected failure"},
        )

        self.assertRedirects(response, f"{self.component.get_absolute_url()}#alerts")
        alert = self.component.alert_set.get(name="BrokenProjectURL")
        self.assertEqual(alert.dismissed_by, self.user)
        self.assertEqual(alert.dismissal_reason, "Expected failure")

    def test_user_without_action_permission_cannot_dismiss_alert(self) -> None:
        self.component.add_alert(
            "BrokenBrowserURL", link="https://example.com", error="failure"
        )

        response = self.client.post(
            reverse("dismiss-alert", kwargs=self.kw_component),
            {"dismiss": "BrokenBrowserURL"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertIsNone(
            self.component.alert_set.get(name="BrokenBrowserURL").dismissed_at
        )

    def test_repository_maintainer_can_dismiss_repository_alert(self) -> None:
        role = Role.objects.create(name="Repository alert maintainer")
        role.permissions.add(Permission.objects.get(codename="vcs.push"))
        group = Group.objects.create(name="Repository alert maintainers")
        group.roles.add(role)
        group.components.add(self.component)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.assertFalse(self.user.has_perm("component.edit", self.component))
        self.assertTrue(self.user.has_perm("meta:vcs.status", self.component))
        self.component.add_alert("RepositoryChanges")

        response = self.client.post(
            reverse("dismiss-alert", kwargs=self.kw_component),
            {"dismiss": "RepositoryChanges"},
        )

        self.assertRedirects(response, f"{self.component.get_absolute_url()}#alerts")
        self.assertEqual(
            self.component.alert_set.get(name="RepositoryChanges").dismissed_by,
            self.user,
        )

    def test_commit_permission_cannot_act_on_outdated_repository(self) -> None:
        role = Role.objects.create(name="Repository commit maintainer")
        role.permissions.add(Permission.objects.get(codename="vcs.commit"))
        group = Group.objects.create(name="Repository commit maintainers")
        group.roles.add(role)
        group.components.add(self.component)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.component.add_alert("RepositoryOutdated")

        alert = self.component.alert_set.get(name="RepositoryOutdated")
        self.assertTrue(self.user.has_perm("meta:vcs.status", self.component))
        self.assertFalse(alert.obj.can_user_act(self.user, self.component))

    def test_screenshot_maintainer_can_dismiss_unused_screenshot(self) -> None:
        role = Role.objects.create(name="Unused screenshot alert maintainer")
        role.permissions.add(Permission.objects.get(codename="screenshot.delete"))
        group = Group.objects.create(name="Unused screenshot alert maintainers")
        group.roles.add(role)
        group.components.add(self.component)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.assertFalse(self.user.has_perm("component.edit", self.component))
        self.assertTrue(self.user.has_perm("screenshot.delete", self.component))
        self.component.add_alert("UnusedScreenshot")

        response = self.client.post(
            reverse("dismiss-alert", kwargs=self.kw_component),
            {"dismiss": "UnusedScreenshot"},
        )

        self.assertRedirects(response, f"{self.component.get_absolute_url()}#alerts")
        self.assertEqual(
            self.component.alert_set.get(name="UnusedScreenshot").dismissed_by,
            self.user,
        )

    def test_language_manager_can_dismiss_ambiguous_language(self) -> None:
        role = Role.objects.create(name="Ambiguous language alert maintainer")
        role.permissions.add(Permission.objects.get(codename="language.edit"))
        group = Group.objects.create(name="Ambiguous language alert maintainers")
        group.roles.add(role)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.assertTrue(self.user.has_perm("language.edit"))
        self.assertFalse(self.user.has_perm("component.edit", self.component))
        self.component.add_alert("AmbiguousLanguage")

        response = self.client.post(
            reverse("dismiss-alert", kwargs=self.kw_component),
            {"dismiss": "AmbiguousLanguage"},
        )

        self.assertRedirects(response, f"{self.component.get_absolute_url()}#alerts")
        self.assertEqual(
            self.component.alert_set.get(name="AmbiguousLanguage").dismissed_by,
            self.user,
        )

    def test_source_editor_can_dismiss_safe_html_alert(self) -> None:
        role = Role.objects.create(name="Safe HTML alert maintainer")
        role.permissions.add(Permission.objects.get(codename="source.edit"))
        group = Group.objects.create(name="Safe HTML alert maintainers")
        group.roles.add(role)
        group.components.add(self.component)
        self.user.groups.add(group)
        self.user.clear_permissions_cache()
        self.assertFalse(self.user.has_perm("component.edit", self.component))
        self.assertTrue(self.user.has_perm("source.edit", self.component))
        self.component.add_alert("MissingSafeHTMLFlag")

        response = self.client.post(
            reverse("dismiss-alert", kwargs=self.kw_component),
            {"dismiss": "MissingSafeHTMLFlag"},
        )

        self.assertRedirects(response, f"{self.component.get_absolute_url()}#alerts")
        self.assertEqual(
            self.component.alert_set.get(name="MissingSafeHTMLFlag").dismissed_by,
            self.user,
        )

    def test_reopen_dismissed_alert_on_details_change(self) -> None:
        self.component.add_alert("BrokenProjectURL", error="first failure")
        alert = self.component.alert_set.get(name="BrokenProjectURL")
        old_timestamp = timezone.now() - timedelta(days=30)
        self.component.alert_set.filter(pk=alert.pk).update(timestamp=old_timestamp)
        alert.refresh_from_db()
        self.assertTrue(alert.dismiss(self.user, "Known issue"))

        self.component.add_alert("BrokenProjectURL", error="different failure")

        alert.refresh_from_db()
        self.assertIsNone(alert.dismissed_at)
        self.assertIsNone(alert.dismissed_by)
        self.assertEqual(alert.dismissal_reason, "")
        self.assertEqual(alert.dismissal_fingerprint, "")
        self.assertGreater(alert.timestamp, old_timestamp)
        self.assertEqual(
            self.component.change_set.filter(
                action=ActionEvents.ALERT_REOPENED, alert=alert
            ).count(),
            1,
        )

        self.component.add_alert("BrokenProjectURL", error="different failure")
        self.assertEqual(
            self.component.change_set.filter(
                action=ActionEvents.ALERT_REOPENED, alert=alert
            ).count(),
            1,
        )

    def test_legacy_dismissal_reopens_on_first_refresh(self) -> None:
        self.component.add_alert("BrokenProjectURL", error="failure")
        alert = self.component.alert_set.get(name="BrokenProjectURL")
        alert.dismissed_at = timezone.now()
        alert.save(update_fields=["dismissed_at"])

        self.component.add_alert("BrokenProjectURL", error="failure")

        alert.refresh_from_db()
        self.assertIsNone(alert.dismissed_at)
        self.assertTrue(
            self.component.change_set.filter(
                action=ActionEvents.ALERT_REOPENED, alert=alert
            ).exists()
        )

    def test_migrated_dismissal_stays_dismissed_on_unchanged_refresh(self) -> None:
        migration = importlib.import_module(
            "weblate.trans.migrations.0094_alert_lifecycle"
        )
        self.component.project.web = "https://example.com/first"
        self.component.project.save(update_fields=["web"])
        self.component.add_alert("BrokenProjectURL", error="failure")
        alert = self.component.alert_set.get(name="BrokenProjectURL")

        migration.backfill_dismissals(self.component.alert_set.filter(pk=alert.pk))
        self.component.add_alert("BrokenProjectURL", error="failure")

        alert.refresh_from_db()
        self.assertIsNotNone(alert.dismissed_at)
        self.assertNotEqual(alert.dismissal_fingerprint, "")
        self.assertFalse(
            self.component.change_set.filter(
                action=ActionEvents.ALERT_REOPENED, alert=alert
            ).exists()
        )

        self.component.project.web = "https://example.com/second"
        self.component.project.save(update_fields=["web"])
        self.component.add_alert("BrokenProjectURL", error="failure")

        alert.refresh_from_db()
        self.assertIsNone(alert.dismissed_at)
        self.assertTrue(
            self.component.change_set.filter(
                action=ActionEvents.ALERT_REOPENED, alert=alert
            ).exists()
        )

    def test_migrated_addon_dismissal_ignores_new_addon_id(self) -> None:
        migration = importlib.import_module(
            "weblate.trans.migrations.0094_alert_lifecycle"
        )
        occurrence = {
            "addon": "weblate.gettext.msgmerge",
            "error": "failure",
        }
        self.component.add_alert("MsgmergeAddonError", occurrences=[occurrence])
        alert = self.component.alert_set.get(name="MsgmergeAddonError")

        migration.backfill_dismissals(self.component.alert_set.filter(pk=alert.pk))
        self.component.add_alert(
            "MsgmergeAddonError",
            occurrences=[{**occurrence, "addon_id": "123"}],
        )

        alert.refresh_from_db()
        self.assertIsNotNone(alert.dismissed_at)
        self.assertNotEqual(alert.dismissal_fingerprint, "")
        self.assertFalse(
            self.component.change_set.filter(
                action=ActionEvents.ALERT_REOPENED, alert=alert
            ).exists()
        )

        self.component.add_alert(
            "MsgmergeAddonError",
            occurrences=[
                {**occurrence, "addon_id": "123", "error": "different failure"}
            ],
        )

        alert.refresh_from_db()
        self.assertIsNone(alert.dismissed_at)
        self.assertTrue(
            self.component.change_set.filter(
                action=ActionEvents.ALERT_REOPENED, alert=alert
            ).exists()
        )

    def test_legacy_dismissal_reopens_on_details_change(self) -> None:
        self.component.add_alert("BrokenProjectURL", error="original failure")
        alert = self.component.alert_set.get(name="BrokenProjectURL")
        alert.dismissed_at = timezone.now()
        alert.save(update_fields=["dismissed_at"])

        self.component.add_alert("BrokenProjectURL", error="different failure")

        alert.refresh_from_db()
        self.assertIsNone(alert.dismissed_at)
        self.assertTrue(
            self.component.change_set.filter(
                action=ActionEvents.ALERT_REOPENED, alert=alert
            ).exists()
        )

    def test_inexact_hook_match_reopens_on_repository_change(self) -> None:
        details = {
            "service_long_name": "Gitea",
            "repo_url": "https://example.com/owner/repo",
            "branch": "main",
            "full_name": "owner/repo",
        }
        self.component.repo = "https://example.com/first/repo.git"
        self.component.save(update_fields=["repo"])
        self.component.add_alert("InexactHookMatch", **details)
        alert = self.component.alert_set.get(name="InexactHookMatch")
        self.assertTrue(alert.dismiss(self.user))

        self.component.repo = "https://example.com/different/repo.git"
        self.component.save(update_fields=["repo"])
        self.component.add_alert("InexactHookMatch", **details)

        alert.refresh_from_db()
        self.assertIsNone(alert.dismissed_at)
        self.assertTrue(
            self.component.change_set.filter(
                action=ActionEvents.ALERT_REOPENED, alert=alert
            ).exists()
        )

    def test_existing_alert_updates_last_seen(self) -> None:
        self.component.add_alert("MissingLicense")
        alert = self.component.alert_set.get(name="MissingLicense")
        old_updated = timezone.now() - timedelta(days=1)
        self.component.alert_set.filter(pk=alert.pk).update(updated=old_updated)

        self.component.add_alert("MissingLicense")

        alert.refresh_from_db()
        self.assertGreater(alert.updated, old_updated)

    def test_inexact_hook_match_alert_exact_history(self) -> None:
        self.component.repo = "https://example.com/owner/repo.git"
        self.component.save()
        self.component.change_set.create(
            action=ActionEvents.HOOK,
            details={
                "service_long_name": "Gitea",
                "repo_url": "https://example.com/owner/repo",
                "repos": ["https://example.com/owner/repo.git"],
                "branch": "main",
                "full_name": "owner/repo",
            },
        )

        update_alerts(self.component, {"InexactHookMatch"})

        self.assertFalse(
            self.component.alert_set.filter(name="InexactHookMatch").exists()
        )

    def test_inexact_hook_match_alert_inferred_history(self) -> None:
        self.component.repo = "https://example.com/owner/repo.git"
        self.component.save()
        self.component.change_set.create(
            action=ActionEvents.HOOK,
            details={
                "service_long_name": "Gitea",
                "repo_url": "https://other.example.com/owner/repo",
                "repos": ["https://other.example.com/owner/repo.git"],
                "branch": "main",
                "full_name": "owner/repo",
            },
        )

        update_alerts(self.component, {"InexactHookMatch"})

        alert = self.component.alert_set.get(name="InexactHookMatch")
        self.assertEqual(alert.severity, AlertSeverity.WARNING)
        self.assertEqual(alert.details["service_long_name"], "Gitea")
        self.assertEqual(alert.details["full_name"], "owner/repo")

    def test_inexact_hook_match_alert_configure_link(self) -> None:
        self.component.add_alert(
            "InexactHookMatch",
            service_long_name="Gitea",
            repo_url="https://example.com/owner/repo",
            branch="main",
            full_name="owner/repo",
        )
        alert = self.component.alert_set.get(name="InexactHookMatch")

        rendered = alert.render(self.user)
        self.assertNotIn("Configure component", rendered)

        self.user.is_superuser = True
        self.user.save()

        rendered = alert.render(self.user)
        self.assertIn("Configure component", rendered)
        self.assertIn(reverse("settings", kwargs=self.kw_component), rendered)

    def test_inexact_hook_match_alert_explicit_match_method(self) -> None:
        self.component.repo = "https://example.com/owner/repo.git"
        self.component.save()
        self.component.change_set.create(
            action=ActionEvents.HOOK,
            details={
                "service_long_name": "Gitea",
                "repo_url": "https://example.com/owner/repo",
                "repos": ["https://example.com/owner/repo.git"],
                "branch": "main",
                "full_name": "owner/repo",
                "match_method": "fallback",
            },
        )

        update_alerts(self.component, {"InexactHookMatch"})

        self.assertTrue(
            self.component.alert_set.filter(name="InexactHookMatch").exists()
        )

        self.component.change_set.create(
            action=ActionEvents.HOOK,
            details={
                "service_long_name": "Gitea",
                "repo_url": "https://example.com/owner/repo",
                "repos": ["https://example.com/owner/repo.git"],
                "branch": "main",
                "full_name": "owner/repo",
                "match_method": "exact",
            },
        )
        update_alerts(self.component, {"InexactHookMatch"})

        self.assertFalse(
            self.component.alert_set.filter(name="InexactHookMatch").exists()
        )

    def test_view(self) -> None:
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Duplicated translation")

    @override_settings(LICENSE_REQUIRED=True)
    def test_license(self) -> None:
        def has_license_alert(component):
            return component.alert_set.filter(name="MissingLicense").exists()

        # No license and public project
        component = self.component
        update_alerts(component)
        self.assertTrue(has_license_alert(component))

        # Private project
        component.project.access_control = component.project.ACCESS_PRIVATE
        update_alerts(component)
        self.assertFalse(has_license_alert(component))

        # Public, but login required
        component.project.access_control = component.project.ACCESS_PUBLIC
        with override_settings(REQUIRE_LOGIN=True):
            update_alerts(component)
            self.assertFalse(has_license_alert(component))

        # Filtered licenses
        with override_settings(LICENSE_FILTER=set()):
            update_alerts(component)
            self.assertFalse(has_license_alert(component))

        # Filtered licenses
        with override_settings(LICENSE_FILTER={"proprietary"}):
            update_alerts(component)
            self.assertTrue(has_license_alert(component))

        # Set license
        component.license = "license"
        update_alerts(component)
        self.assertFalse(has_license_alert(component))

    def test_monolingual(self) -> None:
        component = self.component
        component.update_alerts()
        self.assertFalse(
            component.alert_set.filter(name="MonolingualTranslation").exists()
        )

    def test_duplicate_mask(self) -> None:
        component = self.component
        self.assertFalse(component.alert_set.filter(name="DuplicateFilemask").exists())
        response = self.client.get(component.get_absolute_url())
        self.assertNotContains(
            response, "The following files were found multiple times"
        )

        other = self.create_link_existing()

        self.update_component_alerts(component)
        self.assertTrue(component.alert_set.filter(name="DuplicateFilemask").exists())
        response = self.client.get(component.get_absolute_url())
        self.assertContains(response, "The following files were found multiple times")

        with self.captureOnCommitCallbacks(execute=True):
            other.delete()
        self.update_component_alerts(component)

        self.assertFalse(component.alert_set.filter(name="DuplicateFilemask").exists())

    def test_inexistent_files_reject_symlinked_auxiliary_file(self) -> None:
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(b"outside repository")
        self.addCleanup(os.unlink, handle.name)

        self.component.new_base = "alert-base.pot"
        self.component.save(update_fields=["new_base"])
        os.symlink(
            handle.name, os.path.join(self.component.full_path, "alert-base.pot")
        )

        update_alerts(self.component, {"InexistantFiles"})

        alert = self.component.alert_set.get(name="InexistantFiles")
        self.assertEqual(alert.details["files"], ["alert-base.pot"])


class NoMaskMatchesAlertTest(ViewTestCase):
    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_rescan_adds_alert_when_mask_and_new_base_missing(self) -> None:
        self.assertFalse(self.component.alert_set.filter(name="NoMaskMatches").exists())

        for filename in Path(self.component.full_path, "po").glob("*.po"):
            filename.unlink(missing_ok=True)
        Path(cast("str", self.component.get_new_base_filename())).unlink(
            missing_ok=True
        )

        self.component.create_translations_immediate(force=True)

        translations = list(
            self.component.translation_set.values_list("language_code", "filename")
        )
        self.assertEqual(translations, [("en", "po/hello.pot")])
        self.assertTrue(self.component.alert_set.filter(name="NoMaskMatches").exists())


class AlertQueryPrefetchTest(ViewTestCase):
    def test_project_repo_components_prefetch_all_alerts(self) -> None:
        self._create_component(
            "po",
            "po-link/*.po",
            project=self.project,
            name="LinkedRepo",
        )
        self.create_json(project=self.project, name="JSONRepo")

        project = Project.objects.get(pk=self.project.pk)
        components = project.all_repo_components

        self.assertEqual(len(components), 3)
        with self.assertNumQueries(0):
            alert_maps = [component.all_alerts for component in components]

        self.assertEqual(len(alert_maps), 3)

    def test_linked_children_prefetch_all_alerts(self) -> None:
        self.create_link_existing(name="Linked A", slug="linked-a")
        self.create_link_existing(name="Linked B", slug="linked-b")

        component = Component.objects.get(pk=self.component.pk)
        children = list(component.linked_children)

        self.assertEqual(len(children), 2)
        with self.assertNumQueries(0):
            alert_maps = [child.all_alerts for child in children]

        self.assertEqual(len(alert_maps), 2)


@override_settings(
    GITHUB_CREDENTIALS={
        "api.github.com": {
            "username": "test",
            "token": "token",
        }
    }
)
class ConflictingRepositorySetupAlertTest(ViewTestCase):
    @staticmethod
    def clear_vcs_registry_cache() -> None:
        VCS_REGISTRY.clear_cache()

    def create_component(self):
        return self.create_po()

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        cls.clear_vcs_registry_cache()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.clear_vcs_registry_cache()
        super().tearDownClass()

    def create_conflicting_component(self, **kwargs) -> Component:
        name = kwargs.pop("name", "Test2")
        push = kwargs.pop("push", None)
        component = self._create_component(
            "po",
            "po/*.po",
            project=self.project,
            name=name,
            **kwargs,
        )
        config_kwargs = {}
        if push is not None:
            config_kwargs["push"] = push
        self.configure_merge_request_component(component, **config_kwargs)
        return component

    def configure_merge_request_component(self, component: Component, **kwargs) -> None:
        defaults = {"vcs": "github", "push_branch": "weblate-test"}
        defaults.update(kwargs)
        Component.objects.filter(pk=component.pk).update(**defaults)
        component.refresh_from_db()

    def test_conflicting_repository_setup_for_git_push_branch(self) -> None:
        other = self._create_component(
            "po",
            "po/*.po",
            project=self.project,
            name="Test2",
        )
        Component.objects.filter(pk__in=(self.component.pk, other.pk)).update(
            push_branch="weblate-test"
        )
        self.component.refresh_from_db()
        other.refresh_from_db()

        update_alerts(self.component, {"ConflictingRepositorySetup"})
        update_alerts(other, {"ConflictingRepositorySetup"})

        alert = self.component.alert_set.get(name="ConflictingRepositorySetup")
        self.assertEqual(alert.details["component_ids"], [other.pk])
        self.assertTrue(
            other.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

    def test_conflicting_repository_setup_ignored_for_git_default_push_branch(
        self,
    ) -> None:
        other = self._create_component(
            "po",
            "po/*.po",
            project=self.project,
            name="Test2",
        )

        update_alerts(self.component, {"ConflictingRepositorySetup"})
        update_alerts(other, {"ConflictingRepositorySetup"})

        self.assertFalse(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )
        self.assertFalse(
            other.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

    def test_conflicting_repository_setup_for_mixed_git_push_branch(self) -> None:
        other = self._create_component(
            "po",
            "po/*.po",
            project=self.project,
            name="Test2",
        )
        Component.objects.filter(pk=self.component.pk).update(
            push_branch="weblate-test"
        )
        Component.objects.filter(pk=other.pk).update(branch="weblate-test")
        self.component.refresh_from_db()
        other.refresh_from_db()

        update_alerts(self.component, {"ConflictingRepositorySetup"})
        update_alerts(other, {"ConflictingRepositorySetup"})

        alert = self.component.alert_set.get(name="ConflictingRepositorySetup")
        self.assertEqual(alert.details["component_ids"], [other.pk])
        alert = other.alert_set.get(name="ConflictingRepositorySetup")
        self.assertEqual(alert.details["component_ids"], [self.component.pk])

    def test_conflicting_repository_setup_ignored_for_different_git_branch(
        self,
    ) -> None:
        other = self._create_component(
            "po",
            "po/*.po",
            project=self.project,
            name="Test2",
        )
        Component.objects.filter(pk=other.pk).update(branch="weblate-test-2")
        other.refresh_from_db()

        update_alerts(self.component, {"ConflictingRepositorySetup"})
        update_alerts(other, {"ConflictingRepositorySetup"})

        self.assertFalse(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )
        self.assertFalse(
            other.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

    def test_conflicting_repository_setup_removed_from_peer_on_git_branch_save(
        self,
    ) -> None:
        other = self._create_component(
            "po",
            "po/*.po",
            project=self.project,
            name="Test2",
        )
        Component.objects.filter(pk=self.component.pk).update(
            push_branch="weblate-test"
        )
        Component.objects.filter(pk=other.pk).update(branch="weblate-test")
        self.component.refresh_from_db()
        other.refresh_from_db()

        update_alerts(self.component, {"ConflictingRepositorySetup"})
        update_alerts(other, {"ConflictingRepositorySetup"})
        self.assertTrue(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

        other.branch = "translations"
        other.filemask = "translations/*.po"
        with (
            patch.object(Component, "queue_background_task", return_value=None),
            self.captureOnCommitCallbacks(execute=True),
        ):
            other.save()

        self.assertFalse(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

    def test_conflicting_repository_setup(self) -> None:
        self.configure_merge_request_component(self.component)
        other = self.create_conflicting_component()

        update_alerts(self.component, {"ConflictingRepositorySetup"})
        update_alerts(other, {"ConflictingRepositorySetup"})

        alert = self.component.alert_set.get(name="ConflictingRepositorySetup")
        self.assertEqual(alert.details["component_ids"], [other.pk])
        self.assertTrue(
            other.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "same repository and push branch")
        self.assertContains(response, self.component.get_repo_link_url())

    def test_conflicting_repository_setup_ignored_for_forks(self) -> None:
        self.configure_merge_request_component(self.component, push="")
        other = self.create_conflicting_component(push="")

        update_alerts(self.component, {"ConflictingRepositorySetup"})
        update_alerts(other, {"ConflictingRepositorySetup"})

        self.assertFalse(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )
        self.assertFalse(
            other.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

    def test_conflicting_repository_setup_removed_after_branch_change(self) -> None:
        self.configure_merge_request_component(self.component)
        other = self.create_conflicting_component()

        update_alerts(self.component, {"ConflictingRepositorySetup"})
        self.assertTrue(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

        Component.objects.filter(pk=other.pk).update(push_branch="weblate-test-2")
        other.refresh_from_db()

        update_alerts(self.component, {"ConflictingRepositorySetup"})
        update_alerts(other, {"ConflictingRepositorySetup"})

        self.assertFalse(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

    def test_conflicting_repository_setup_removed_from_peer_on_save(self) -> None:
        self.configure_merge_request_component(self.component)
        other = self.create_conflicting_component()

        update_alerts(self.component, {"ConflictingRepositorySetup"})
        update_alerts(other, {"ConflictingRepositorySetup"})
        self.assertTrue(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

        other.push_branch = "weblate-test-2"
        with (
            patch.object(Component, "queue_background_task", return_value=None),
            self.captureOnCommitCallbacks(execute=True),
        ):
            other.save()

        self.assertFalse(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

    def test_conflicting_repository_setup_removed_from_peer_on_delete(self) -> None:
        self.configure_merge_request_component(self.component)
        other = self.create_conflicting_component()

        update_alerts(self.component, {"ConflictingRepositorySetup"})
        update_alerts(other, {"ConflictingRepositorySetup"})
        self.assertTrue(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

        other.delete()

        self.assertFalse(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

    def test_conflicting_repository_setup_not_removed_from_peer_on_unrelated_save(
        self,
    ) -> None:
        self.configure_merge_request_component(self.component)
        other = self.create_conflicting_component()

        update_alerts(self.component, {"ConflictingRepositorySetup"})
        update_alerts(other, {"ConflictingRepositorySetup"})

        other.name = "Renamed"
        with patch.object(Component, "queue_background_task", return_value=None):
            other.save()

        self.assertTrue(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

    def test_conflicting_repository_setup_not_removed_from_peer_on_pull_branch_save(
        self,
    ) -> None:
        self.configure_merge_request_component(self.component)
        other = self.create_conflicting_component()

        update_alerts(self.component, {"ConflictingRepositorySetup"})
        update_alerts(other, {"ConflictingRepositorySetup"})

        other.branch = "translations"
        with patch.object(Component, "queue_background_task", return_value=None):
            other.save()

        self.assertTrue(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )

    def test_conflicting_repository_setup_kept_for_remaining_peers_on_delete(
        self,
    ) -> None:
        self.configure_merge_request_component(self.component)
        other = self.create_conflicting_component()
        third = self.create_conflicting_component(name="Test3")

        for component in (self.component, other, third):
            update_alerts(component, {"ConflictingRepositorySetup"})

        other.delete()

        self.assertTrue(
            self.component.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )
        self.assertTrue(
            third.alert_set.filter(name="ConflictingRepositorySetup").exists()
        )


class LanguageAlertTest(ViewTestCase):
    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_ambiguous_language(self) -> None:
        component = self.component
        self.assertFalse(component.alert_set.filter(name="AmbiguousLanguage").exists())
        with self.captureOnCommitCallbacks(execute=True):
            component.add_new_language(
                Language.objects.get(code="ku"), self.get_request()
            )
        update_alerts(component)
        self.assertTrue(component.alert_set.filter(name="AmbiguousLanguage").exists())


class ExtractPotAlertTest(ViewTestCase):
    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_missing_msgmerge_alert(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        with self.captureOnCommitCallbacks(execute=True):
            XgettextAddon.create(
                component=self.component,
                run=False,
                configuration={
                    "interval": "weekly",
                    "update_po_files": False,
                    "language": "Python",
                    "source_patterns": ["src/*.py"],
                },
            )
        update_alerts(self.component)

        self.assertTrue(
            self.component.alert_set.filter(name="ExtractPotMissingMsgmerge").exists()
        )

    def test_missing_msgmerge_alert_cleared_by_project_msgmerge(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        self.component.update_alerts()
        MsgmergeAddon.create(project=self.component.project, run=False)
        self.component.refresh_from_db()

        self.assertFalse(
            self.component.alert_set.filter(name="ExtractPotMissingMsgmerge").exists()
        )

    def test_missing_msgmerge_alert_ignores_inherited_incompatible_extractor(
        self,
    ) -> None:
        SphinxAddon.create(
            project=self.component.project,
            run=False,
            configuration={
                "interval": "weekly",
                "normalize_header": False,
                "filter_mode": "none",
            },
        )

        self.component.update_alerts()

        self.assertFalse(
            self.component.alert_set.filter(name="ExtractPotMissingMsgmerge").exists()
        )

    def test_missing_msgmerge_alert_ignores_invalid_addon(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        with self.captureOnCommitCallbacks(execute=True):
            XgettextAddon.create(
                component=self.component,
                run=False,
                configuration={
                    "interval": "weekly",
                    "language": "Python",
                    "source_patterns": ["src/*.py"],
                },
            )
        Addon.objects.bulk_create(
            [Addon(component=self.component, name="weblate.addon.nonexisting")]
        )

        update_alerts(self.component)

        self.assertTrue(
            self.component.alert_set.filter(name="ExtractPotMissingMsgmerge").exists()
        )

    def test_unrelated_addon_does_not_reopen_missing_msgmerge_alert(self) -> None:
        XgettextAddon.create(
            component=self.component,
            run=False,
            configuration={
                "interval": "weekly",
                "update_po_files": False,
                "language": "Python",
                "source_patterns": ["src/*.py"],
            },
        )
        update_alerts(self.component, {"ExtractPotMissingMsgmerge"})
        alert = self.component.alert_set.get(name="ExtractPotMissingMsgmerge")
        self.assertTrue(alert.dismiss(self.user))

        Addon.objects.create(
            component=self.component,
            name="weblate.cleanup.generic",
        )
        update_alerts(self.component, {"ExtractPotMissingMsgmerge"})

        alert.refresh_from_db()
        self.assertIsNotNone(alert.dismissed_at)
        self.assertFalse(
            self.component.change_set.filter(
                action=ActionEvents.ALERT_REOPENED,
                alert=alert,
            ).exists()
        )


class MonolingualAlertTest(ViewTestCase):
    def create_component(self):
        return self.create_po_mono()

    def test_monolingual(self) -> None:
        self.assertFalse(
            self.component.alert_set.filter(name="MonolingualTranslation").exists()
        )
        self.assertFalse(
            self.component.alert_set.filter(
                name="BilingualPOConfiguredAsMonolingual"
            ).exists()
        )

    def test_false_bilingual(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            component = self._create_component(
                "po-mono", "po-mono/*.po", project=self.project, name="bimono"
            )
        update_alerts(component)
        self.assertTrue(
            component.alert_set.filter(name="MonolingualTranslation").exists()
        )
        self.assertFalse(
            component.alert_set.filter(
                name="BilingualPOConfiguredAsMonolingual"
            ).exists()
        )

    def test_bilingual_po_configured_as_monolingual(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            component = self._create_component(
                "po-mono",
                "po/*.po",
                "po/hello.pot",
                project=self.project,
                name="bilingual-po-as-mono",
            )
        update_alerts(component)
        self.assertTrue(
            component.alert_set.filter(
                name="BilingualPOConfiguredAsMonolingual"
            ).exists()
        )

    def test_bilingual_po_configured_as_monolingual_ignores_glossary(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            component = self._create_component(
                "po-mono",
                "po/*.po",
                "po/hello.pot",
                project=self.project,
                name="glossary-po-as-mono",
            )
        component.is_glossary = True
        update_alerts(component, {"BilingualPOConfiguredAsMonolingual"})
        self.assertFalse(
            component.alert_set.filter(
                name="BilingualPOConfiguredAsMonolingual"
            ).exists()
        )


class RepositoryAlertTemplateTest(SimpleTestCase):
    def test_repository_guidance_uses_header_documentation_link(self) -> None:
        for template_name in (
            "trans/alert/repositoryoutdated.html",
            "trans/alert/repositorychanges.html",
        ):
            with self.subTest(template_name=template_name):
                rendered = render_to_string(template_name)

                self.assertNotIn("Documentation", rendered)
                self.assertNotIn("btn btn-primary", rendered)

    def test_bilingual_po_configured_as_monolingual_guidance(self) -> None:
        rendered = render_to_string(
            "trans/alert/bilingualpoconfiguredasmonolingual.html",
        )

        self.assertIn(
            "regular gettext PO files, but it is configured as monolingual",
            rendered,
        )
        self.assertIn("change the file format to gettext PO file", rendered)

    def test_no_mask_matches_explains_empty_repository_state(self) -> None:
        rendered = render_to_string(
            "trans/alert/nomaskmatches.html",
            {
                "analysis": {"can_add": True},
                "component": SimpleNamespace(filemask="po/*.po"),
            },
        )

        self.assertIn(
            "This is okay when the repository does not contain translations yet.",
            rendered,
        )
        self.assertIn(
            "The alert will disappear once translations are added in Weblate or "
            "committed to the repository.",
            rendered,
        )
        self.assertIn("If translations already exist", rendered)

    def test_broken_project_url_renders_validation_error_as_main_message(
        self,
    ) -> None:
        rendered = render_to_string(
            "trans/alert/brokenprojecturl.html",
            {
                "component": SimpleNamespace(
                    project=SimpleNamespace(web="https://weblate.contact.de")
                ),
                "error": (
                    "This URL is prohibited because it points to an internal or "
                    "non-public address."
                ),
            },
        )

        self.assertIn(
            "Weblate could not validate the project website URL:",
            rendered,
        )
        self.assertIn(
            "This URL is prohibited because it points to an internal or non-public "
            "address.",
            rendered,
        )
        self.assertNotIn("non-existing location", rendered)

    def test_broken_browser_url_renders_validation_error_as_main_message(
        self,
    ) -> None:
        rendered = render_to_string(
            "trans/alert/brokenbrowserurl.html",
            {
                "link": "https://weblate.contact.de/source/file.po",
                "error": (
                    "This URL is prohibited because it points to an internal or "
                    "non-public address."
                ),
            },
        )

        self.assertIn(
            "Weblate could not validate the repository browser URL:",
            rendered,
        )
        self.assertIn(
            "This URL is prohibited because it points to an internal or non-public "
            "address.",
            rendered,
        )
        self.assertNotIn("non-existing location", rendered)

    def test_update_failure_analysis_uses_component_host_key_message(self) -> None:
        component = SimpleNamespace(
            get_ssh_host_key_mismatch_error_message=lambda: "host key changed",
            get_ssh_host_key_error_message=lambda: "host key missing",
            push="",
            repo="",
            vcs="git",
            merge_style="merge",
            push_branch="",
        )
        alert = UpdateFailure(
            cast("Alert", SimpleNamespace(component=component)),
            "REMOTE HOST IDENTIFICATION HAS CHANGED!\nHost key verification failed.\n",
        )

        self.assertEqual(alert.get_analysis()["host_key_message"], "host key changed")

    def test_common_repo_renders_host_key_mismatch_message(self) -> None:
        rendered = render_to_string(
            "trans/alert/common-repo.html",
            {
                "analysis": {
                    "behind": False,
                    "force_push_suggestion": False,
                    "gerrit": False,
                    "host_key_message": (
                        "The SSH host key for the repository has changed. "
                        "Verify the new fingerprint, remove the stored host key, "
                        "and add the new one on the SSH page in the admin interface."
                    ),
                    "not_found": False,
                    "permission": False,
                    "repo_suggestion": None,
                    "temporary": False,
                    "terminal": False,
                }
            },
        )

        self.assertIn(
            "The SSH host key for the repository has changed.",
            rendered,
        )
