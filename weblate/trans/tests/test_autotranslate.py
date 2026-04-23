# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for automatic translation."""

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test.utils import override_settings
from django.urls import reverse

from weblate.addons.autotranslate import AutoTranslateAddon
from weblate.addons.events import AddonEvent
from weblate.addons.models import AddonActivityLog
from weblate.lang.models import Language, Plural
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change, Component, PendingUnitChange, Project, Unit
from weblate.trans.tasks import auto_translate, auto_translate_component
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_READONLY, STATE_TRANSLATED
from weblate.utils.stats import ProjectLanguage


class AutoTranslationTest(ViewTestCase):
    use_component_id: bool = False

    def setUp(self) -> None:
        super().setUp()
        # Need extra power
        self.user.is_superuser = True
        self.user.save()
        self.project.translation_review = True
        self.project.save()
        self.component2 = self.create_second_component()

    def create_second_component(self, project: Project | None = None) -> Component:
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            return Component.objects.create(
                name="Test 2",
                slug="test-2",
                project=self.project if project is None else project,
                repo=self.git_repo_path,
                push=self.git_repo_path,
                vcs="git",
                filemask="po/*.po",
                template="",
                file_format="po",
                new_base="",
                allow_translation_propagation=False,
            )

    def create_autotranslate_activity_log(
        self, component: Component | None = None
    ) -> AddonActivityLog:
        if component is None:
            component = self.component2
        addon = AutoTranslateAddon.create(
            component=component,
            run=False,
            configuration={
                "component": self.component.id,
                "q": "state:<translated",
                "auto_source": "others",
                "engines": [],
                "threshold": 100,
                "mode": "translate",
            },
        )
        return AddonActivityLog.objects.create(
            addon=addon.instance,
            component=component,
            event=AddonEvent.EVENT_COMPONENT_UPDATE,
            pending=True,
        )

    def test_none(self) -> None:
        """Test for automatic translation with no content."""
        response = self.client.post(
            reverse("auto_translation", kwargs=self.kw_translation)
        )
        self.assertRedirects(response, self.translation_url)

    def make_different(self, language: str = "cs") -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", language=language)

    def set_mismatched_plural(self) -> None:
        source_translation = self.get_translation()
        source_translation.plural = source_translation.language.plural_set.create(
            source=Plural.SOURCE_GETTEXT,
            number=2,
            formula="(n != 1)",
        )
        source_translation.save(update_fields=["plural"])

    def translate_plural_source(self) -> None:
        plural_unit = self.get_unit("Orangutan has %d banana.\n")
        plural_unit.translate(
            self.user,
            [
                "Orangutan ma %d banan.\n",
                "Orangutani maji %d banany.\n",
            ],
            STATE_TRANSLATED,
        )

    def perform_auto(
        self, expected=1, expected_count=None, path_params=None, success=True, **kwargs
    ) -> None:
        self.make_different()
        if path_params is None:
            path_params = {"path": [*self.component2.get_url_path(), "cs"]}
        url = reverse("auto_translation", kwargs=path_params)
        kwargs["auto_source"] = "others"
        kwargs["threshold"] = "100"
        if "q" not in kwargs:
            kwargs["q"] = "state:<translated"
        if "mode" not in kwargs:
            kwargs["mode"] = "translate"
        if self.use_component_id:
            kwargs["component"] = self.component.id
        response = self.client.post(url, kwargs, follow=True)
        if expected == 0:
            expected_string = (
                "Automatic translation completed, no strings were updated."
            )
        elif expected == 1:
            expected_string = "Automatic translation completed, 1 string was updated."
        else:
            expected_string = (
                f"Automatic translation completed, {expected} strings were updated."
            )

        if success:
            self.assertRedirects(response, reverse("show", kwargs=path_params))
            self.assertContains(response, expected_string)

        # Check we've translated something
        translation = self.component2.translation_set.get(language_code="cs")
        translation.invalidate_cache()
        if expected_count is None:
            expected_count = expected
        if kwargs["mode"] == "suggest":
            self.assertEqual(translation.stats.suggestions, expected_count)
        elif kwargs["mode"] == "fuzzy":
            self.assertEqual(translation.stats.fuzzy, expected_count)
        else:
            self.assertEqual(translation.stats.translated, expected_count)

    def test_different(self) -> None:
        """Test for automatic translation with different content."""
        self.perform_auto()

    def test_readonly_empty_target_source_candidate(self) -> None:
        """Skip source candidates with empty targets even when read-only."""
        source_unit = self.get_unit("Hello, world!\n")
        Unit.objects.filter(pk=source_unit.pk).update(
            state=STATE_READONLY,
            target="",
        )
        translation = self.component2.translation_set.get(language_code="cs")
        target_unit = self.get_unit("Hello, world!\n", translation=translation)
        initial_pending = PendingUnitChange.objects.filter(unit=target_unit).count()

        result = auto_translate(
            translation_id=translation.id,
            user_id=self.user.id,
            mode="translate",
            q="state:<translated",
            auto_source="others",
            source_component_id=self.component.id,
            engines=[],
            threshold=100,
        )

        self.assertEqual(
            result["message"],
            "Automatic translation completed, no strings were updated.",
        )
        target_unit.refresh_from_db()
        self.assertEqual(target_unit.target, "")
        self.assertFalse(target_unit.automatically_translated)
        self.assertEqual(
            PendingUnitChange.objects.filter(unit=target_unit).count(),
            initial_pending,
        )

    def test_plural_mismatch_warning(self) -> None:
        self.set_mismatched_plural()
        self.edit_unit("Thank you for using Weblate.", "Diky za pouzivani Weblate.")
        self.translate_plural_source()
        path_params = {"path": [*self.component2.get_url_path(), "cs"]}

        response = self.client.post(
            reverse("auto_translation", kwargs=path_params),
            {
                "auto_source": "others",
                "component": self.component.id,
                "threshold": "100",
                "q": "state:<translated",
                "mode": "translate",
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("show", kwargs=path_params))
        self.assertContains(
            response,
            "Automatic translation completed, 1 string was updated.",
        )
        self.assertContains(response, "do not match the target translation")

        translation = self.component2.translation_set.get(language_code="cs")
        singular = self.get_unit(
            "Thank you for using Weblate.", translation=translation
        )
        self.assertEqual(singular.target, "Diky za pouzivani Weblate.")
        target_plural = self.get_unit(
            "Orangutan has %d banana.\n", translation=translation
        )
        self.assertEqual(target_plural.get_target_plurals(), ["", "", ""])

    def test_plural_mismatch_task_warning(self) -> None:
        self.set_mismatched_plural()
        self.edit_unit("Thank you for using Weblate.", "Diky za pouzivani Weblate.")
        self.translate_plural_source()
        activity_log = self.create_autotranslate_activity_log()

        result = auto_translate(
            translation_id=self.component2.translation_set.get(language_code="cs").id,
            user_id=self.user.id,
            mode="translate",
            q="state:<translated",
            auto_source="others",
            source_component_id=self.component.id,
            engines=[],
            threshold=100,
            activity_log_id=activity_log.id,
        )

        self.assertEqual(
            result["message"],
            "Automatic translation completed, 1 string was updated.",
        )
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("do not match the target translation", result["warnings"][0])
        activity_log.refresh_from_db()
        self.assertFalse(activity_log.pending)
        self.assertEqual(
            activity_log.details["result"]["message"],
            "Automatic translation completed, 1 string was updated.",
        )
        self.assertEqual(len(activity_log.details["result"]["warnings"]), 1)
        self.assertIn(
            "do not match the target translation",
            activity_log.details["result"]["warnings"][0],
        )

    def test_autotranslate_missing_target_returns_result_dict(self) -> None:
        translation = self.component2.translation_set.get(language_code="cs")
        translation_id = translation.id
        translation.delete()

        result = auto_translate(
            translation_id=translation_id,
            user_id=self.user.id,
            mode="translate",
            q="state:<translated",
            auto_source="others",
            source_component_id=self.component.id,
            engines=[],
            threshold=100,
        )

        self.assertEqual(
            result,
            {
                "message": "Automatic translation skipped because the target no longer exists.",
                "warnings": [],
            },
        )

    def test_suggest(self) -> None:
        """Test for automatic suggestion."""
        self.perform_auto(mode="suggest")
        self.perform_auto(0, 1, mode="suggest")

    def test_approved(self) -> None:
        """Test for automatic suggestion."""
        self.perform_auto(mode="approved")
        self.perform_auto(0, 1, mode="approved")

    def test_fuzzy(self) -> None:
        """Test for automatic suggestion in fuzzy mode."""
        self.perform_auto(mode="fuzzy")

    def test_inconsistent(self) -> None:
        self.perform_auto(0, q="check:inconsistent")

    def test_overwrite(self) -> None:
        self.perform_auto(overwrite="1")

    def test_autotranslate_component(self) -> None:
        self.make_different("de")
        de_translation = self.component2.translation_set.get(language_code="de")
        initial_stats = de_translation.stats.translated
        self.perform_auto(
            path_params={"path": self.component2.get_url_path()},
            expected=2,
            expected_count=1,  # we only expect one new translation in 'cs'
        )
        de_translation.invalidate_cache()
        self.assertEqual(de_translation.stats.translated, initial_stats + 1)

    def test_autotranslate_category(self) -> None:
        self.component.category = self.create_category(project=self.project)
        category = self.component.category
        if self.component2.project != self.project:
            category = self.create_category(project=self.component2.project)
        self.component2.category = category
        self.component.save()
        self.component2.save()

        self.make_different("de")

        self.perform_auto(
            path_params={"path": category.get_url_path()},
            expected=2,
            expected_count=1,  # we only expect one new translation in 'cs'
        )

    def test_autotranslate_project_language(self) -> None:
        project_language = ProjectLanguage(
            self.component2.project,
            language=Language.objects.get(code="cs"),
        )
        self.make_different("de")

        self.perform_auto(
            path_params={"path": project_language.get_url_path()},
            expected_count=1,
            expected=1,
        )

    def test_autotranslate_fail(self) -> None:
        # invalid object type
        self.perform_auto(
            expected=0, path_params={"path": self.project.get_url_path()}, success=False
        )

        self.user.is_superuser = False
        self.user.save()

        # test missing autotranslate permission on translation
        self.perform_auto(expected=0, success=False)

        # test missing autotranslate permission on project language
        project_language = ProjectLanguage(
            self.project,
            language=Language.objects.get(code="cs"),
        )
        self.perform_auto(
            expected=0,
            path_params={"path": project_language.get_url_path()},
            success=False,
        )

        # test missing autotranslate permission on category
        category = self.create_category(project=self.project)
        self.component.category = self.component2.category = category
        self.component.save()
        self.perform_auto(
            path_params={"path": category.get_url_path()}, expected=0, success=False
        )
        self.perform_auto(
            path_params={"path": self.component.get_url_path()},
            expected=0,
            success=False,
        )

        # test invalid arguments
        with self.assertRaises(ValueError):
            auto_translate(
                user_id=None,
                mode="suggest",
                q="state:<translated",
                auto_source="others",
                source_component_id=None,
                engines=["weblate"],
                threshold=100,
            )

        with self.assertRaises(ValueError):
            auto_translate(
                user_id=None,
                mode="suggest",
                q="state:<translated",
                auto_source="others",
                source_component_id=None,
                engines=["weblate"],
                threshold=100,
                project_id=1,
            )

    def test_labeling(self) -> None:
        self.perform_auto(overwrite="1")
        translation = self.component2.translation_set.get(language_code="cs")
        self.assertEqual(
            translation.unit_set.filter(automatically_translated=True).count(),
            1,
        )
        self.edit_unit("Thank you for using Weblate.", "Díky za používání Weblate.")
        self.assertEqual(
            translation.unit_set.filter(automatically_translated=True).count(),
            1,
        )
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", translation=translation)
        self.assertEqual(
            translation.unit_set.filter(automatically_translated=True).count(),
            0,
        )

    def test_automatically_translated_column(self) -> None:
        """Test that automatically_translated column is set correctly."""
        translation = self.component2.translation_set.get(language_code="cs")
        self.assertEqual(
            translation.unit_set.filter(automatically_translated=True).count(),
            0,
        )

        self.perform_auto(overwrite="1")

        auto_unit = translation.unit_set.filter(automatically_translated=True).first()
        self.assertIsNotNone(auto_unit)
        self.assertTrue(auto_unit.automatically_translated)

        auto_unit.translate(
            self.user,
            "Manually edited translation",
            auto_unit.state,
        )

        auto_unit.refresh_from_db()
        self.assertFalse(auto_unit.automatically_translated)

        self.assertEqual(
            translation.unit_set.filter(automatically_translated=True).count(),
            0,
        )

    def test_autotranslate_creates_change_and_pending(self) -> None:
        """Auto-translation creates Change and PendingUnitChange records in bulk."""
        self.make_different()
        translation = self.component2.translation_set.get(language_code="cs")

        initial_change_count = Change.objects.count()
        initial_pending_count = PendingUnitChange.objects.count()

        self.perform_auto()

        self.assertGreater(Change.objects.count(), initial_change_count)
        self.assertTrue(Change.objects.filter(action=ActionEvents.AUTO).exists())
        self.assertGreater(PendingUnitChange.objects.count(), initial_pending_count)
        auto_translated_unit = translation.unit_set.get(automatically_translated=True)
        self.assertTrue(
            PendingUnitChange.objects.filter(unit=auto_translated_unit).exists()
        )

    def test_autotranslate_component_uses_supplied_user(self) -> None:
        self.make_different()
        translation = self.component2.translation_set.get(language_code="cs")

        auto_translate_component(
            self.component2.id,
            mode="translate",
            q="state:<translated",
            auto_source="others",
            engines=[],
            threshold=100,
            source_component_id=self.component.id,
            user_id=self.user.id,
        )

        auto_translated_unit = translation.unit_set.get(automatically_translated=True)
        self.assertEqual(
            auto_translated_unit.change_set.get(action=ActionEvents.AUTO).author,
            self.user,
        )
        self.assertTrue(
            PendingUnitChange.objects.filter(
                unit=auto_translated_unit,
                author=self.user,
                automatically_translated=True,
            ).exists()
        )

    def test_autotranslate_component_stores_activity_log_result(self) -> None:
        self.make_different()
        activity_log = self.create_autotranslate_activity_log()

        result = auto_translate_component(
            self.component2.id,
            mode="translate",
            q="state:<translated",
            auto_source="others",
            engines=[],
            threshold=100,
            source_component_id=self.component.id,
            user_id=self.user.id,
            activity_log_id=activity_log.id,
        )

        self.assertEqual(
            result["message"],
            "Automatic translation completed, 1 string was updated.",
        )
        self.assertEqual(result["warnings"], [])
        activity_log.refresh_from_db()
        self.assertFalse(activity_log.pending)
        self.assertEqual(activity_log.details["result"], result)

    def test_command(self) -> None:
        call_command("auto_translate", "test", "test", "cs")

    def test_command_add_error(self) -> None:
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "ia", add=True)

    def test_command_mt(self) -> None:
        call_command("auto_translate", "--mt", "weblate", "test", "test", "cs")

    def test_command_mt_error(self) -> None:
        with self.assertRaises(CommandError):
            call_command("auto_translate", "--mt", "invalid", "test", "test", "ia")
        with self.assertRaises(CommandError):
            call_command(
                "auto_translate", "--threshold", "invalid", "test", "test", "ia"
            )

    def test_command_add(self) -> None:
        self.component.file_format = "po"
        self.component.new_lang = "add"
        self.component.new_base = "po/cs.po"
        self.component.clean()
        self.component.save()
        call_command("auto_translate", "test", "test", "ia", add=True)
        self.assertTrue(
            self.component.translation_set.filter(language__code="ia").exists()
        )

    def test_command_different(self) -> None:
        self.make_different()
        call_command(
            "auto_translate",
            self.component2.project.slug,
            self.component2.slug,
            "cs",
            source=self.component.full_slug,
        )

    def test_command_errors(self) -> None:
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "cs", user="invalid")
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "cs", source="invalid")
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "cs", source="test/invalid")
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "xxx")


class AutoTranslationCrossProjectTest(AutoTranslationTest):
    use_component_id: bool = True

    def create_second_component(self, project: Project | None = None) -> Component:
        project = Project.objects.create(
            name="Other", slug="other", translation_review=True
        )
        return super().create_second_component(project=project)


class AutoTranslationMtTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        # Need extra power
        self.user.is_superuser = True
        self.user.save()
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            self.component3 = Component.objects.create(
                name="Test 3",
                slug="test-3",
                project=self.project,
                repo=self.git_repo_path,
                push=self.git_repo_path,
                vcs="git",
                filemask="po/*.po",
                template="",
                file_format="po",
                new_base="",
                allow_translation_propagation=False,
            )
        self.update_fulltext_index()
        self.configure_mt()

    def test_none(self) -> None:
        """Test for automatic translation with no content."""
        url = reverse("auto_translation", kwargs=self.kw_translation)
        response = self.client.post(url)
        self.assertRedirects(response, self.translation_url)

    def make_different(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")

    def perform_auto(self, expected=1, **kwargs) -> None:
        self.make_different()
        path_params = {"path": [*self.component3.get_url_path(), "cs"]}
        url = reverse("auto_translation", kwargs=path_params)
        kwargs["auto_source"] = "mt"
        if "q" not in kwargs:
            kwargs["q"] = "state:<translated"
        if "mode" not in kwargs:
            kwargs["mode"] = "translate"
        response = self.client.post(url, kwargs, follow=True)
        if expected == 1:
            self.assertContains(
                response, "Automatic translation completed, 1 string was updated."
            )
        else:
            self.assertContains(
                response, "Automatic translation completed, no strings were updated."
            )

        self.assertRedirects(response, reverse("show", kwargs=path_params))
        # Check we've translated something
        translation = self.component3.translation_set.get(language_code="cs")
        translation.invalidate_cache()
        self.assertEqual(translation.stats.translated, expected)

    def test_different(self) -> None:
        """Test for automatic translation with different content."""
        self.perform_auto(engines=["weblate"], threshold=80)

    def test_mt_origin_uses_mt_user(self) -> None:
        self.perform_auto(engines=["weblate"], threshold=80)

        translation = self.component3.translation_set.get(language_code="cs")
        auto_translated_unit = translation.unit_set.get(automatically_translated=True)
        author = auto_translated_unit.change_set.get(action=ActionEvents.AUTO).author

        self.assertIsNotNone(author)
        self.assertEqual(getattr(author, "username", None), "mt:weblate")
        self.assertTrue(getattr(author, "is_bot", False))

    def test_multi(self) -> None:
        """Test for automatic translation with more providers."""
        self.perform_auto(
            engines=["weblate", "weblate-translation-memory"], threshold=80
        )

    def test_inconsistent(self) -> None:
        self.perform_auto(0, q="check:inconsistent", engines=["weblate"], threshold=80)

    def test_overwrite(self) -> None:
        self.perform_auto(overwrite="1", engines=["weblate"], threshold=80)
