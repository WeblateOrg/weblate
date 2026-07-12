# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for component guidance alerts."""

import os
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils.functional import cached_property

from weblate.addons.gettext import XgettextAddon
from weblate.screenshots.models import Screenshot
from weblate.trans.alerts.base import AlertSeverity, BaseAlert
from weblate.trans.alerts.community import (
    AddonRecommendationAlert,
    ChecklistAlert,
    MissingRepositoryHook,
    MissingSafeHTMLFlag,
    MissingScreenshots,
    MissingTranslationFlags,
    MissingTranslationInstructions,
    RecommendedConfigureAddon,
    RecommendedDjangoAddon,
    RecommendedGenerateMoAddon,
    RecommendedLinguasAddon,
    RecommendedMesonAddon,
    RecommendedSphinxAddon,
    RecommendedXgettextAddon,
)
from weblate.trans.alerts.config import MissingLicense, UnusedScreenshot
from weblate.trans.alerts.registry import get_alert_class, update_alerts
from weblate.trans.alerts.vcs import RepositoryOutdated
from weblate.trans.models import Project
from weblate.trans.templatetags.translations import component_alerts
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.docs import get_doc_url


class RecommendedGenerateMoAddonTest(SimpleTestCase):
    def test_recommendation_ignores_invalid_translation_file(self) -> None:
        component = Mock()
        component.source_translation.id = 1
        translation = Mock()
        translation.get_filename.side_effect = ValidationError(
            "Invalid symbolic link in a repository."
        )
        component.translation_set.exclude.return_value = [translation]

        with patch.object(AddonRecommendationAlert, "is_relevant", return_value=True):
            self.assertFalse(RecommendedGenerateMoAddon.is_relevant(component))


class ExtractorGuidanceAlertTest(ViewTestCase):
    @cached_property
    def git_repo_path(self) -> str:
        path = self.get_repo_path("test-guidance-repo.git")
        if os.path.exists(path):
            shutil.rmtree(path)
        shutil.copytree(self.git_base_repo_path, path)
        return path

    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_xgettext_recommendation(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        alert_class = RecommendedXgettextAddon

        self.assertTrue(alert_class.is_relevant(self.component))

    def test_django_recommendation(self) -> None:
        self.component.new_base = "locale/django.pot"
        self.component.save(update_fields=["new_base"])

        alert_class = RecommendedDjangoAddon

        self.assertTrue(alert_class.is_relevant(self.component))

    def test_sphinx_recommendation(self) -> None:
        self.component.new_base = "docs/locales/docs.pot"
        self.component.save(update_fields=["new_base"])
        docs_dir = Path(self.component.full_path) / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "conf.py").write_text("extensions = []\n", encoding="utf-8")
        (docs_dir / "index.rst").write_text("Heading\n=======\n", encoding="utf-8")

        alert_class = RecommendedSphinxAddon

        self.assertTrue(alert_class.is_relevant(self.component))

    def test_meson_recommendation(self) -> None:
        self.component.new_base = "po/messages.pot"
        self.component.save(update_fields=["new_base"])
        gettext_dir = Path(self.component.full_path) / "po"
        gettext_dir.mkdir(parents=True, exist_ok=True)
        (Path(self.component.full_path) / "meson.build").write_text(
            "project('test', 'c')\n", encoding="utf-8"
        )
        (gettext_dir / "meson.build").write_text("", encoding="utf-8")
        (gettext_dir / "POTFILES.in").write_text("src/main.c\n", encoding="utf-8")

        alert_class = RecommendedMesonAddon

        self.assertTrue(alert_class.is_relevant(self.component))

    def test_guidance_alert_severity(self) -> None:
        source = Path(self.component.full_path) / "src" / "messages.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            'from gettext import gettext as _\n_("Hello")\n', encoding="utf-8"
        )
        update_alerts(
            self.component,
            {
                MissingTranslationInstructions.__name__,
                RecommendedXgettextAddon.__name__,
            },
        )

        self.assertEqual(
            self.component.alert_set.get(
                name=MissingTranslationInstructions.__name__
            ).severity,
            AlertSeverity.WARNING,
        )
        self.assertEqual(
            self.component.alert_set.get(
                name=RecommendedXgettextAddon.__name__
            ).severity,
            AlertSeverity.INFO,
        )

    def test_guidance_alert_severity_and_dismissibility(self) -> None:
        expected = (
            (MissingSafeHTMLFlag, AlertSeverity.WARNING),
            (MissingScreenshots, AlertSeverity.INFO),
            (MissingTranslationFlags, AlertSeverity.INFO),
            (RecommendedConfigureAddon, AlertSeverity.INFO),
            (RecommendedDjangoAddon, AlertSeverity.INFO),
            (RecommendedGenerateMoAddon, AlertSeverity.INFO),
            (RecommendedLinguasAddon, AlertSeverity.INFO),
            (RecommendedMesonAddon, AlertSeverity.INFO),
            (RecommendedSphinxAddon, AlertSeverity.INFO),
            (RecommendedXgettextAddon, AlertSeverity.INFO),
            (UnusedScreenshot, AlertSeverity.WARNING),
        )

        for alert_class, severity in expected:
            with self.subTest(alert=alert_class.__name__):
                self.assertEqual(alert_class.severity, severity)
                self.assertTrue(alert_class.dismissible)

    def test_guidance_base_requires_passing_implementation(self) -> None:
        with self.assertRaises(NotImplementedError):
            ChecklistAlert.is_passing(self.component)

    def test_base_alert_empty_details_are_not_passing(self) -> None:
        class EmptyDetailsAlert(BaseAlert):
            @staticmethod
            def check_component(_component: object) -> dict[str, object]:
                return {}

        self.assertFalse(EmptyDetailsAlert.is_passing(self.component))

    def test_project_configure_uses_project_permission(self) -> None:
        alert_name = MissingTranslationInstructions.__name__
        self.component.add_alert(alert_name)
        alert = self.component.alert_set.get(name=alert_name)
        user = Mock(is_authenticated=True)
        user.has_perm.return_value = True

        context = MissingTranslationInstructions(alert).get_context(user)

        user.has_perm.assert_called_once_with("project.edit", self.component.project)
        self.assertTrue(context["can_configure"])
        self.assertEqual(
            context["configure_url"],
            reverse("settings", kwargs={"path": self.component.project.get_url_path()}),
        )

    def test_duplicate_configure_url_is_documentation_only(self) -> None:
        alert_name = MissingRepositoryHook.__name__
        self.component.add_alert(alert_name)
        alert = self.component.alert_set.get(name=alert_name)
        self.make_manager()

        rendered = MissingRepositoryHook(alert).render(self.user)
        doc_url = MissingRepositoryHook.get_doc_url(self.component, self.user)

        self.assertNotIn("btn btn-primary", rendered)
        self.assertNotIn(doc_url, rendered)
        self.assertEqual(alert.get_documentation_url(self.user), doc_url)

        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, doc_url, count=1)

    def test_unused_screenshot_does_not_make_component_problem(self) -> None:
        alert_name = UnusedScreenshot.__name__
        problem_alerts = {alert.name for alert in self.component.all_problem_alerts}
        self.component.add_alert(alert_name)

        alert = self.component.alert_set.get(name=alert_name)

        self.assertEqual(alert.severity, AlertSeverity.WARNING)
        self.assertEqual(
            {alert.name for alert in self.component.all_problem_alerts},
            problem_alerts,
        )

    def test_dismissed_unused_screenshot_visible_with_all_alerts(self) -> None:
        alert_name = UnusedScreenshot.__name__
        self.component.add_alert(alert_name)
        alert = self.component.alert_set.get(name=alert_name)
        alert.dismissed = True
        alert.save(update_fields=["dismissed"])
        self.component.__dict__.pop("all_active_alerts", None)

        self.assertNotIn(
            alert_name, {alert.name for alert in self.component.all_active_alerts}
        )
        response = self.client.get(f"{self.component.get_absolute_url()}?alerts=1")
        self.assertContains(response, "Unused screenshot")

    def test_component_diagnostics_are_ordered(self) -> None:
        self.component.add_alert(RepositoryOutdated.__name__)
        self.component.add_alert(UnusedScreenshot.__name__)
        self.component.add_alert(MissingLicense.__name__)
        self.component.add_alert(MissingScreenshots.__name__)

        alert = self.component.alert_set.get(name=UnusedScreenshot.__name__)
        alert.dismissed = True
        alert.save(update_fields=["dismissed"])

        response = self.client.get(self.component.get_absolute_url())
        alert_names = [alert.name for alert in response.context["alerts"]]
        content = response.content.decode()
        repository_alert = self.component.alert_set.get(
            name=RepositoryOutdated.__name__
        )
        license_alert = self.component.alert_set.get(name=MissingLicense.__name__)
        license_doc_url = get_doc_url(
            "admin/projects", "component-license", user=self.user
        )

        self.assertContains(response, "License info missing.")
        self.assertContains(response, "Repository outdated.")
        self.assertContains(
            response, repository_alert.get_documentation_url(self.user), count=1
        )
        self.assertEqual(
            license_alert.get_documentation_url(self.user), license_doc_url
        )
        self.assertEqual(
            MissingLicense.get_doc_url(self.component), "https://choosealicense.com/"
        )
        self.assertContains(response, license_doc_url, count=1)
        self.assertContains(
            response, "Add screenshots to show where strings are being used."
        )
        self.assertNotContains(response, "Unused screenshot")
        self.assertContains(
            response,
            '<span class="badge text-bg-danger">2'
            '<span class="visually-hidden">errors</span></span>',
            html=True,
        )
        self.assertContains(
            response, '<span class="badge text-bg-info">Information</span>', html=True
        )
        self.assertEqual(response.context["problem_alerts_count"], 2)
        self.assertLess(
            content.index("License info missing."),
            content.index("Repository outdated."),
        )
        self.assertLess(
            content.index("Repository outdated."),
            content.index("Add screenshots to show where strings are being used."),
        )
        self.assertEqual(
            alert_names,
            [
                MissingLicense.__name__,
                RepositoryOutdated.__name__,
                MissingScreenshots.__name__,
            ],
        )

        response = self.client.get(f"{self.component.get_absolute_url()}?alerts=1")
        alert_names = [alert.name for alert in response.context["alerts"]]
        content = response.content.decode()

        self.assertContains(
            response, '<span class="badge text-bg-warning">Warning</span>', html=True
        )
        self.assertLess(
            content.index("Repository outdated."),
            content.index("Unused screenshot"),
        )
        self.assertLess(
            content.index("Unused screenshot"),
            content.index("Add screenshots to show where strings are being used."),
        )
        self.assertEqual(
            alert_names,
            [
                MissingLicense.__name__,
                RepositoryOutdated.__name__,
                UnusedScreenshot.__name__,
                MissingScreenshots.__name__,
            ],
        )

    def test_guidance_alert_removed_when_passing(self) -> None:
        alert_name = MissingTranslationInstructions.__name__
        update_alerts(self.component, {alert_name})
        self.assertTrue(self.component.alert_set.filter(name=alert_name).exists())

        self.component.project.instructions = "Translate clearly."
        self.component.project.save(update_fields=["instructions"])

        self.assertFalse(self.component.alert_set.filter(name=alert_name).exists())

    def test_translation_instructions_guidance_not_created_on_project_save(
        self,
    ) -> None:
        alert_name = MissingTranslationInstructions.__name__
        self.component.project.instructions = "Translate clearly."
        self.component.project.save(update_fields=["instructions"])
        self.component.project.instructions = ""
        self.component.project.save(update_fields=["instructions"])

        self.assertFalse(self.component.alert_set.filter(name=alert_name).exists())

    def test_translation_instructions_guidance_not_created_when_access_opens(
        self,
    ) -> None:
        alert_name = MissingTranslationInstructions.__name__
        self.component.project.access_control = Project.ACCESS_PRIVATE
        self.component.project.save(update_fields=["access_control"])
        self.component.project.access_control = Project.ACCESS_PUBLIC
        self.component.project.save(update_fields=["access_control"])

        self.assertFalse(self.component.alert_set.filter(name=alert_name).exists())

    @override_settings(REQUIRE_LOGIN=True)
    def test_translation_instructions_cleanup_not_run_on_unrelated_project_save(
        self,
    ) -> None:
        self.component.project.name = "Renamed project"

        with patch.object(
            Project, "_clear_translation_instructions_guidance_alert"
        ) as clear_alert:
            self.component.project.save(update_fields=["name"])

        clear_alert.assert_not_called()

    def test_translation_instructions_guidance_removed_when_access_closes(
        self,
    ) -> None:
        alert_name = MissingTranslationInstructions.__name__
        self.component.add_alert(alert_name)

        self.component.project.access_control = Project.ACCESS_PRIVATE
        self.component.project.save(update_fields=["access_control"])

        self.assertFalse(self.component.alert_set.filter(name=alert_name).exists())

    def test_translation_instructions_relevant_for_protected_project(self) -> None:
        alert_name = MissingTranslationInstructions.__name__
        self.component.project.access_control = Project.ACCESS_PROTECTED
        self.component.project.save(update_fields=["access_control"])

        update_alerts(self.component, {alert_name})

        self.assertTrue(self.component.alert_set.filter(name=alert_name).exists())

    def test_translation_instructions_ignored_for_private_project(self) -> None:
        alert_name = MissingTranslationInstructions.__name__
        self.component.project.access_control = Project.ACCESS_PRIVATE
        self.component.project.save(update_fields=["access_control"])

        update_alerts(self.component, {alert_name})

        self.assertFalse(self.component.alert_set.filter(name=alert_name).exists())

    @override_settings(REQUIRE_LOGIN=True)
    def test_translation_instructions_ignored_when_login_required(self) -> None:
        alert_name = MissingTranslationInstructions.__name__

        update_alerts(self.component, {alert_name})

        self.assertFalse(self.component.alert_set.filter(name=alert_name).exists())

    def test_screenshot_guidance_still_relevant_for_private_project(self) -> None:
        alert_name = MissingScreenshots.__name__
        self.component.project.access_control = Project.ACCESS_PRIVATE
        self.component.project.save(update_fields=["access_control"])

        update_alerts(self.component, {alert_name})

        self.assertTrue(self.component.alert_set.filter(name=alert_name).exists())

    def test_translation_flags_guidance_still_relevant_for_private_project(
        self,
    ) -> None:
        alert_name = MissingTranslationFlags.__name__
        self.component.check_flags = ""
        self.component.save(update_fields=["check_flags"])
        self.component.source_translation.unit_set.update(extra_flags="")
        self.component.project.access_control = Project.ACCESS_PRIVATE
        self.component.project.save(update_fields=["access_control"])

        update_alerts(self.component, {alert_name})

        self.assertTrue(self.component.alert_set.filter(name=alert_name).exists())

    def test_screenshot_guidance_removed_when_screenshot_is_added(self) -> None:
        alert_name = MissingScreenshots.__name__
        self.component.add_alert(alert_name)

        Screenshot.objects.create(
            name="Screenshot",
            image="screenshots/test.png",
            translation=self.component.source_translation,
        )

        self.assertFalse(self.component.alert_set.filter(name=alert_name).exists())

    def test_screenshot_guidance_not_created_when_screenshot_is_deleted(self) -> None:
        alert_name = MissingScreenshots.__name__
        screenshot = Screenshot.objects.create(
            name="Screenshot",
            image="screenshots/test.png",
            translation=self.component.source_translation,
        )
        screenshot.delete()

        self.assertFalse(self.component.alert_set.filter(name=alert_name).exists())

    def test_addon_guidance_removed_when_addon_is_added(self) -> None:
        alert_name = RecommendedXgettextAddon.__name__
        self.component.add_alert(alert_name)

        XgettextAddon.create(component=self.component, run=False)

        self.assertFalse(self.component.alert_set.filter(name=alert_name).exists())

    def test_addon_guidance_not_created_when_addon_is_removed(self) -> None:
        alert_name = RecommendedXgettextAddon.__name__
        addon = XgettextAddon.create(component=self.component, run=False)
        addon.instance.delete()

        self.assertFalse(self.component.alert_set.filter(name=alert_name).exists())

    def test_existing_component_alert_removed_from_registry(self) -> None:
        with self.assertRaises(KeyError):
            get_alert_class("ExistingComponentAlerts")

    def test_guidance_alert_shows_tab_without_problem_indicator(self) -> None:
        self.component.alert_set.all().delete()
        self.component.__dict__.pop("all_alerts", None)
        self.component.__dict__.pop("all_active_alerts", None)
        self.component.__dict__.pop("all_problem_alerts", None)

        update_alerts(self.component, {MissingTranslationInstructions.__name__})

        self.assertTrue(self.component.all_active_alerts)
        self.assertFalse(self.component.all_problem_alerts)
        self.assertFalse(list(component_alerts(self.component)))
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, 'data-bs-target="#alerts"')
        self.assertEqual(response.context["problem_alerts_count"], 0)
        self.assertNotContains(response, "text-bg-danger")
