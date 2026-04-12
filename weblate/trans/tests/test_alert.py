# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for alerts."""

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from weblate.addons.gettext import MsgmergeAddon, SphinxAddon, XgettextAddon
from weblate.addons.models import Addon
from weblate.lang.models import Language
from weblate.trans.models import Component, Unit
from weblate.trans.models.alert import UpdateFailure, update_alerts
from weblate.trans.tests.test_views import ViewTestCase
from weblate.vcs.models import VCS_REGISTRY


class WebsiteAlertSettingTest(ViewTestCase):
    """Test WEBSITE_ALERTS_ENABLED setting."""

    def create_component(self):
        return self._create_component("po", "po/*.po")

    @override_settings(WEBSITE_ALERTS_ENABLED=False)
    @patch("weblate.trans.models.alert.get_uri_error", return_value="unreachable")
    def test_website_alerts_disabled(self, mocked_get_uri_error) -> None:
        """Test that website alerts are not created when setting is False."""
        self.project.web = "https://example.com/project"
        update_alerts(self.component, {"BrokenProjectURL"})
        self.assertFalse(
            self.component.alert_set.filter(name="BrokenProjectURL").exists()
        )
        mocked_get_uri_error.assert_not_called()

    @override_settings(WEBSITE_ALERTS_ENABLED=True)
    @patch("weblate.trans.models.alert.get_uri_error", return_value="unreachable")
    def test_website_alerts_enabled(self, mocked_get_uri_error) -> None:
        """Test that website alerts are created when setting is True."""
        self.project.web = "https://example.com/project"
        update_alerts(self.component, {"BrokenProjectURL"})
        self.assertTrue(
            self.component.alert_set.filter(name="BrokenProjectURL").exists()
        )
        mocked_get_uri_error.assert_called_once_with("https://example.com/project")

    @override_settings(WEBSITE_ALERTS_ENABLED=True)
    @patch("weblate.trans.models.alert.get_uri_error")
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
        "weblate.trans.models.alert.validate_request_url",
        side_effect=ValidationError("URL domain is not allowed."),
    )
    @patch("weblate.trans.models.alert.get_uri_error")
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


class AlertTest(ViewTestCase):
    def create_component(self):
        return self._create_component("po", "po-duplicates/*.dpo", manage_units=True)

    def test_duplicates(self) -> None:
        self.assertEqual(
            set(self.component.alert_set.values_list("name", flat=True)),
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
        unit.translation.delete_unit(None, unit)

        # The alert should have been removed now
        self.assertEqual(
            set(self.component.alert_set.values_list("name", flat=True)),
            {
                "DuplicateLanguage",
                "BrokenBrowserURL",
                "BrokenProjectURL",
            },
        )

    def test_unused_enforced(self) -> None:
        self.assertEqual(
            set(self.component.alert_set.values_list("name", flat=True)),
            {
                "DuplicateLanguage",
                "DuplicateString",
                "BrokenBrowserURL",
                "BrokenProjectURL",
            },
        )
        self.component.enforced_checks = ["es_format"]
        self.component.save()
        self.assertEqual(
            set(self.component.alert_set.values_list("name", flat=True)),
            {
                "DuplicateLanguage",
                "DuplicateString",
                "BrokenBrowserURL",
                "BrokenProjectURL",
                "UnusedEnforcedCheck",
            },
        )

    def test_dismiss(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("dismiss-alert", kwargs=self.kw_component),
            {"dismiss": "BrokenBrowserURL"},
        )
        self.assertRedirects(response, f"{self.component.get_absolute_url()}#alerts")
        self.assertTrue(self.component.alert_set.get(name="BrokenBrowserURL").dismissed)

    def test_view(self) -> None:
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, "Duplicated translation")

    @override_settings(LICENSE_REQUIRED=True)
    def test_license(self) -> None:
        def has_license_alert(component):
            return component.alert_set.filter(name="MissingLicense").exists()

        # No license and public project
        component = self.component
        component.update_alerts()
        self.assertTrue(has_license_alert(component))

        # Private project
        component.project.access_control = component.project.ACCESS_PRIVATE
        component.update_alerts()
        self.assertFalse(has_license_alert(component))

        # Public, but login required
        component.project.access_control = component.project.ACCESS_PUBLIC
        with override_settings(LOGIN_REQUIRED_URLS=["some"]):
            component.update_alerts()
            self.assertFalse(has_license_alert(component))

        # Filtered licenses
        with override_settings(LICENSE_FILTER=set()):
            component.update_alerts()
            self.assertFalse(has_license_alert(component))

        # Filtered licenses
        with override_settings(LICENSE_FILTER={"proprietary"}):
            component.update_alerts()
            self.assertTrue(has_license_alert(component))

        # Set license
        component.license = "license"
        component.update_alerts()
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

        self.assertTrue(component.alert_set.filter(name="DuplicateFilemask").exists())
        response = self.client.get(component.get_absolute_url())
        self.assertContains(response, "The following files were found multiple times")

        other.delete()

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

        for key in ("data", "merge_request_based", "git_based"):
            VCS_REGISTRY.__dict__.pop(key, None)

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
        with patch.object(Component, "queue_background_task", return_value=None):
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
        component.add_new_language(Language.objects.get(code="ku"), self.get_request())
        component.update_alerts()
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

        self.component.update_alerts()

        self.assertTrue(
            self.component.alert_set.filter(name="ExtractPotMissingMsgmerge").exists()
        )


class MonolingualAlertTest(ViewTestCase):
    def create_component(self):
        return self.create_po_mono()

    def test_monolingual(self) -> None:
        self.assertFalse(
            self.component.alert_set.filter(name="MonolingualTranslation").exists()
        )

    def test_false_bilingual(self) -> None:
        component = self._create_component(
            "po-mono", "po-mono/*.po", project=self.project, name="bimono"
        )
        self.assertTrue(
            component.alert_set.filter(name="MonolingualTranslation").exists()
        )


class RepositoryAlertTemplateTest(SimpleTestCase):
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
            SimpleNamespace(component=component),
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
                        "Verify the new fingerprint and replace the stored host key "
                        "on the SSH page in the admin interface."
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
