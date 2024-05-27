# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os
from datetime import timedelta
from io import StringIO
from unittest import SkipTest

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from weblate.addons.autotranslate import AutoTranslateAddon
from weblate.addons.base import TestAddon, TestCrashAddon, TestError
from weblate.addons.cdn import CDNJSAddon
from weblate.addons.cleanup import CleanupAddon, RemoveBlankAddon
from weblate.addons.consistency import LangaugeConsistencyAddon
from weblate.addons.discovery import DiscoveryAddon
from weblate.addons.example import ExampleAddon
from weblate.addons.example_pre import ExamplePreAddon
from weblate.addons.flags import (
    BulkEditAddon,
    SameEditAddon,
    SourceEditAddon,
    TargetEditAddon,
)
from weblate.addons.generate import (
    FillReadOnlyAddon,
    GenerateFileAddon,
    PrefillAddon,
    PseudolocaleAddon,
)
from weblate.addons.gettext import (
    GenerateMoAddon,
    GettextAuthorComments,
    GettextCustomizeAddon,
    MsgmergeAddon,
    UpdateConfigureAddon,
    UpdateLinguasAddon,
)
from weblate.addons.git import GitSquashAddon
from weblate.addons.json import JSONCustomizeAddon
from weblate.addons.models import ADDONS, Addon
from weblate.addons.properties import PropertiesSortAddon
from weblate.addons.removal import RemoveComments, RemoveSuggestions
from weblate.addons.resx import ResxUpdateAddon
from weblate.addons.tasks import cleanup_addon_activity_log, daily_addons
from weblate.addons.xml import XMLCustomizeAddon
from weblate.addons.yaml import YAMLCustomizeAddon
from weblate.lang.models import Language
from weblate.trans.models import Comment, Component, Suggestion, Translation, Unit, Vote
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_EMPTY, STATE_FUZZY, STATE_READONLY
from weblate.utils.unittest import tempdir_setting


class TestAddonMixin:
    def setUp(self) -> None:
        super().setUp()
        ADDONS.data[TestAddon.name] = TestAddon
        ADDONS.data[ExampleAddon.name] = ExampleAddon
        ADDONS.data[TestCrashAddon.name] = TestCrashAddon
        ADDONS.data[ExamplePreAddon.name] = ExamplePreAddon

    def tearDown(self) -> None:
        super().tearDown()
        del ADDONS.data[TestAddon.name]
        del ADDONS.data[ExampleAddon.name]
        del ADDONS.data[TestCrashAddon.name]
        del ADDONS.data[ExamplePreAddon.name]


class AddonBaseTest(TestAddonMixin, ViewTestCase):
    def test_can_install(self) -> None:
        self.assertTrue(TestAddon.can_install(self.component, None))

    def test_example(self) -> None:
        self.assertTrue(ExampleAddon.can_install(self.component, None))
        addon = ExampleAddon.create(component=self.component)
        addon.pre_commit(None, "")

    def test_create(self) -> None:
        addon = TestAddon.create(component=self.component)
        self.assertEqual(addon.name, "weblate.base.test")
        self.assertEqual(self.component.addon_set.count(), 1)

    def test_create_project_addon(self) -> None:
        self.component.project.acting_user = self.component.acting_user
        addon = TestAddon.create(project=self.component.project)
        self.assertEqual(addon.name, "weblate.base.test")
        self.assertEqual(self.component.project.addon_set.count(), 1)
        self.assertEqual("Test add-on: Test", str(addon.instance))

    def test_create_site_wide_addon(self) -> None:
        addon = TestAddon.create(acting_user=self.user)
        self.assertEqual(addon.name, "weblate.base.test")
        addon_object = Addon.objects.filter(name="weblate.base.test")
        self.assertEqual(addon_object.count(), 1)
        self.assertEqual("Test add-on: site-wide", str(addon.instance))

    def test_add_form(self) -> None:
        form = TestAddon.get_add_form(None, component=self.component, data={})
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual(self.component.addon_set.count(), 1)

        addon = self.component.addon_set.all()[0]
        self.assertEqual(addon.name, "weblate.base.test")

    def test_add_form_project_addon(self) -> None:
        form = TestAddon.get_add_form(None, project=self.component.project, data={})
        self.assertTrue(form.is_valid())
        form.save()
        self.assertEqual(self.component.project.addon_set.count(), 1)

        addon = self.component.project.addon_set.all()[0]
        self.assertEqual(addon.name, "weblate.base.test")

    def test_add_form_site_wide_addon(self) -> None:
        form = TestAddon.get_add_form(None, data={})
        self.assertTrue(form.is_valid())
        form.save()
        addon_object = Addon.objects.filter(name="weblate.base.test")
        self.assertEqual(addon_object.count(), 1)

        addon = addon_object[0]
        self.assertEqual("Test add-on: site-wide", str(addon))


class IntegrationTest(TestAddonMixin, ViewTestCase):
    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_registry(self) -> None:
        GenerateMoAddon.create(component=self.component)
        addon = self.component.addon_set.all()[0]
        self.assertIsInstance(addon.addon, GenerateMoAddon)

    def test_commit(self) -> None:
        GenerateMoAddon.create(component=self.component)
        TestAddon.create(component=self.component)
        rev = self.component.repository.last_revision
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.get_translation().commit_pending("test", None)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("po/cs.mo", commit)

    def test_add(self) -> None:
        UpdateLinguasAddon.create(component=self.component)
        UpdateConfigureAddon.create(component=self.component)
        TestAddon.create(component=self.component)
        rev = self.component.repository.last_revision
        self.component.add_new_language(Language.objects.get(code="sk"), None)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("po/LINGUAS", commit)
        self.assertIn("configure", commit)

    def test_update(self) -> None:
        rev = self.component.repository.last_revision
        MsgmergeAddon.create(component=self.component)
        TestAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        self.component.trigger_post_update(
            self.component.repository.last_revision, False
        )
        self.assertEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("po/cs.po", commit)

    def test_store(self) -> None:
        GettextCustomizeAddon.create(
            component=self.component, configuration={"width": -1}
        )
        rev = self.component.repository.last_revision
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.get_translation().commit_pending("test", None)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn(
            "Last-Translator: Weblate Test <weblate@example.org>\\nLanguage", commit
        )

    def test_crash(self) -> None:
        addon = TestCrashAddon.create(component=self.component)
        self.assertTrue(Addon.objects.filter(name=TestCrashAddon.name).exists())
        ADDONS[TestCrashAddon.get_identifier()] = TestCrashAddon

        with self.assertRaises(TestError):
            addon.post_update(self.component, "head", False, False)

        # The crash should be handled here and addon uninstalled
        self.component.trigger_post_update(
            self.component.repository.last_revision, False
        )

        self.assertFalse(Addon.objects.filter(name=TestCrashAddon.name).exists())

    def test_process_error(self) -> None:
        addon = TestAddon.create(component=self.component)
        addon.execute_process(self.component, ["false"])
        self.assertEqual(len(addon.alerts), 1)


class GettextAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_gettext_mo(self) -> None:
        translation = self.get_translation()
        self.assertTrue(GenerateMoAddon.can_install(translation.component, None))
        addon = GenerateMoAddon.create(component=translation.component)
        addon.pre_commit(translation, "")
        self.assertTrue(os.path.exists(translation.addon_commit_files[0]))

    def test_update_linguas(self) -> None:
        translation = self.get_translation()
        self.assertTrue(UpdateLinguasAddon.can_install(translation.component, None))
        addon = UpdateLinguasAddon.create(component=translation.component)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("LINGUAS", commit)
        self.assertIn("\n+cs\n", commit)
        addon.post_add(translation)
        self.assertEqual(translation.addon_commit_files, [])

        other = self._create_component(
            "po", "po-duplicates/*.dpo", name="Other", project=self.project
        )
        self.assertTrue(UpdateLinguasAddon.can_install(other, None))
        addon = UpdateLinguasAddon.create(component=other)
        commit = other.repository.show(other.repository.last_revision)
        self.assertIn("LINGUAS", commit)
        self.assertIn("\n+cs de it", commit)

    def assert_linguas(self, source, expected_add, expected_remove) -> None:
        # Test no-op
        self.assertEqual(
            UpdateLinguasAddon.update_linguas(source, {"de", "it"}), (False, source)
        )
        # Test adding cs
        self.assertEqual(
            UpdateLinguasAddon.update_linguas(source, {"cs", "de", "it"}),
            (True, expected_add),
        )
        # Test adding cs and removing de
        self.assertEqual(
            UpdateLinguasAddon.update_linguas(source, {"cs", "it"}),
            (True, expected_remove),
        )

    def test_linguas_files_oneline(self) -> None:
        self.assert_linguas(["de it\n"], ["cs de it\n"], ["cs it\n"])

    def test_linguas_files_line(self) -> None:
        self.assert_linguas(
            ["de\n", "it\n"], ["de\n", "it\n", "cs\n"], ["it\n", "cs\n"]
        )

    def test_linguas_files_line_comment(self) -> None:
        self.assert_linguas(
            ["# Linguas list\n", "de\n", "it\n"],
            ["# Linguas list\n", "de\n", "it\n", "cs\n"],
            ["# Linguas list\n", "it\n", "cs\n"],
        )

    def test_linguas_files_inline_comment(self) -> None:
        self.assert_linguas(
            ["de # German\n", "it # Italian\n"],
            ["de # German\n", "it # Italian\n", "cs\n"],
            ["it # Italian\n", "cs\n"],
        )

    def test_update_configure(self) -> None:
        translation = self.get_translation()
        self.assertTrue(UpdateConfigureAddon.can_install(translation.component, None))
        addon = UpdateConfigureAddon.create(component=translation.component)
        addon.post_add(translation)
        self.assertEqual(translation.addon_commit_files, [])

    def test_msgmerge(self, wrapped=True) -> None:
        self.assertTrue(MsgmergeAddon.can_install(self.component, None))
        rev = self.component.repository.last_revision
        addon = MsgmergeAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False, False)
        self.assertEqual(rev, self.component.repository.last_revision)
        addon.post_update(self.component, rev, False, False)
        self.assertEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("po/cs.po", commit)
        self.assertEqual('msgid "Try using Weblate demo' in commit, not wrapped)

    def test_msgmerge_nowrap(self) -> None:
        GettextCustomizeAddon.create(
            component=self.component, configuration={"width": -1}
        )
        self.test_msgmerge(False)

    def test_generate(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.assertTrue(GenerateFileAddon.can_install(self.component, None))
        GenerateFileAddon.create(
            component=self.component,
            configuration={
                "filename": "stats/{{ language_code }}.json",
                "template": """{
    "translated": {{ stats.translated_percent }}
}""",
            },
        )
        self.get_translation().commit_pending("test", None)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("stats/cs.json", commit)
        self.assertIn('"translated": 25', commit)

    def test_gettext_comment(self) -> None:
        translation = self.get_translation()
        self.assertTrue(GettextAuthorComments.can_install(translation.component, None))
        addon = GettextAuthorComments.create(component=translation.component)
        addon.pre_commit(translation, "Stojan Jakotyc <stojan@example.com>")
        with open(translation.get_filename()) as handle:
            content = handle.read()
        self.assertIn("Stojan Jakotyc", content)

    def test_pseudolocale(self) -> None:
        self.assertTrue(PseudolocaleAddon.can_install(self.component, None))
        PseudolocaleAddon.create(
            component=self.component,
            configuration={
                "source": self.component.translation_set.get(language_code="en").pk,
                "target": self.component.translation_set.get(language_code="de").pk,
                "prefix": "@@@",
                "suffix": "!!!",
            },
        )
        translation = self.component.translation_set.get(language_code="de")
        self.assertEqual(translation.stats.translated, translation.stats.all)
        for unit in translation.unit_set.all():
            for text in unit.get_target_plurals():
                self.assertTrue(text.startswith("@@@"))
                # We need to deal with automated fixups
                self.assertTrue(text.endswith(("!!!", "!!!\n")))

    def test_pseudolocale_variable(self) -> None:
        self.assertTrue(PseudolocaleAddon.can_install(self.component, None))
        PseudolocaleAddon.create(
            component=self.component,
            configuration={
                "source": self.component.translation_set.get(language_code="en").pk,
                "target": self.component.translation_set.get(language_code="de").pk,
                "prefix": "@@@",
                "suffix": "!!!",
                "var_prefix": "_",
                "var_suffix": "_",
                "var_multiplier": 1,
            },
        )
        translation = self.component.translation_set.get(language_code="de")
        self.assertEqual(translation.check_flags, "ignore-all-checks")
        self.assertEqual(translation.stats.translated, translation.stats.all)
        for unit in translation.unit_set.all():
            for text in unit.get_target_plurals():
                self.assertTrue(text.startswith("@@@_"))
                # We need to deal with automated fixups
                self.assertTrue(text.endswith(("_!!!", "_!!!\n")))
        for addon in self.component.addon_set.all():
            addon.delete()
        translation = self.component.translation_set.get(language_code="de")
        self.assertEqual(translation.check_flags, "")

    def test_prefill(self) -> None:
        self.assertTrue(PrefillAddon.can_install(self.component, None))
        PrefillAddon.create(component=self.component)
        for translation in self.component.translation_set.prefetch():
            self.assertEqual(translation.stats.nottranslated, 0)
            for unit in translation.unit_set.all():
                sources = unit.get_source_plurals()
                for text in unit.get_target_plurals():
                    self.assertIn(text, sources)
        self.assertFalse(Unit.objects.filter(pending=True).exists())

    def test_read_only(self) -> None:
        self.assertTrue(FillReadOnlyAddon.can_install(self.component, None))
        addon = FillReadOnlyAddon.create(component=self.component)
        for translation in self.component.translation_set.prefetch():
            if translation.is_source:
                continue
            self.assertEqual(translation.stats.readonly, 0)
        unit = self.get_unit().source_unit
        unit.extra_flags = "read-only"
        unit.save(same_content=True, update_fields=["extra_flags"])
        for translation in self.component.translation_set.prefetch():
            if translation.is_source:
                continue
            translation.invalidate_cache()
            self.assertEqual(translation.stats.readonly, 1)
            unit = translation.unit_set.get(state=STATE_READONLY)
            self.assertEqual(unit.target, "")
        addon.daily(self.component)
        for translation in self.component.translation_set.prefetch():
            if translation.is_source:
                continue
            self.assertEqual(translation.stats.readonly, 1)
            unit = translation.unit_set.get(state=STATE_READONLY)
            self.assertEqual(unit.target, unit.source)


class AppStoreAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_appstore()

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(self.component, None))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False, False)
        self.assertEqual(rev, self.component.repository.last_revision)
        addon.post_update(self.component, "", False, False)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("cs/changelogs/100000.txt", commit)


class AndroidAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_android(suffix="-not-synced", new_lang="add")

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(self.component, None))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False, False)
        self.assertEqual(rev, self.component.repository.last_revision)
        addon.post_update(self.component, "", False, False)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("android-not-synced/values-cs/strings.xml", commit)
        self.assertIn('\n-    <string name="hello">Ahoj svete</string>', commit)


class WindowsRCAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_winrc()

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(self.component, None))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False, False)
        self.assertEqual(rev, self.component.repository.last_revision)
        addon.post_update(self.component, "", False, False)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("winrc/cs-CZ.rc", commit)
        self.assertIn("\n-IDS_MSG5", commit)


class IntermediateAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_json_intermediate(new_lang="add")

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(self.component, None))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False, False)
        self.assertEqual(rev, self.component.repository.last_revision)
        addon.post_update(self.component, "", False, False)
        commit = self.component.repository.show(self.component.repository.last_revision)
        # It should remove string not present in the English file
        self.assertIn("intermediate/cs.json", commit)
        self.assertIn('-    "orangutan"', commit)


class ResxAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_resx()

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(self.component, None))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        # Unshallow the local repo
        with self.component.repository.lock:
            self.component.repository.execute(["fetch", "--unshallow", "origin"])
        addon.post_update(
            self.component, "da07dc0dc7052dc44eadfa8f3a2f2609ec634303", False, False
        )
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("resx/cs.resx", commit)

    def test_update(self) -> None:
        self.assertTrue(ResxUpdateAddon.can_install(self.component, None))
        addon = ResxUpdateAddon.create(component=self.component)
        rev = self.component.repository.last_revision
        # Unshallow the local repo
        with self.component.repository.lock:
            self.component.repository.execute(["fetch", "--unshallow", "origin"])
        addon.post_update(
            self.component, "da07dc0dc7052dc44eadfa8f3a2f2609ec634303", False, False
        )
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("resx/cs.resx", commit)


class CSVAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_csv_mono()

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(self.component, None))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        addon.post_update(
            self.component, "da07dc0dc7052dc44eadfa8f3a2f2609ec634303", False, False
        )
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("csv-mono/cs.csv", commit)

    def test_remove_blank(self) -> None:
        self.assertTrue(RemoveBlankAddon.can_install(self.component, None))
        rev = self.component.repository.last_revision
        addon = RemoveBlankAddon.create(component=self.component)
        addon.post_update(
            self.component, "da07dc0dc7052dc44eadfa8f3a2f2609ec634303", False, False
        )
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("csv-mono/cs.csv", commit)


class JsonAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_json_mono(suffix="mono-sync")

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(self.component, None))
        rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False, False)
        self.assertEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("json-mono-sync/cs.json", commit)

    def test_remove_blank(self) -> None:
        self.assertTrue(RemoveBlankAddon.can_install(self.component, None))
        rev = self.component.repository.last_revision
        addon = RemoveBlankAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False, False)
        self.assertEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("json-mono-sync/cs.json", commit)

    def test_unit_flags(self) -> None:
        self.assertTrue(SourceEditAddon.can_install(self.component, None))
        self.assertTrue(TargetEditAddon.can_install(self.component, None))
        self.assertTrue(SameEditAddon.can_install(self.component, None))
        SourceEditAddon.create(component=self.component)
        TargetEditAddon.create(component=self.component)
        SameEditAddon.create(component=self.component)

        Unit.objects.filter(translation__language__code="cs").delete()
        self.component.create_translations(force=True)
        self.assertFalse(
            Unit.objects.filter(translation__language__code="cs")
            .exclude(state__in=(STATE_FUZZY, STATE_EMPTY))
            .exists()
        )

        Unit.objects.all().delete()
        self.component.create_translations(force=True)
        self.assertFalse(
            Unit.objects.exclude(
                state__in=(STATE_FUZZY, STATE_EMPTY, STATE_READONLY)
            ).exists()
        )

    def asset_customize(self, expected: str):
        rev = self.component.repository.last_revision
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.get_translation().commit_pending("test", None)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn(f'{expected}"try"', commit)

    def test_customize(self) -> None:
        JSONCustomizeAddon.create(
            component=self.component,
            configuration={"indent": 8, "sort": 1, "style": "spaces"},
        )
        self.asset_customize("        ")

    def test_customize_sitewide(self) -> None:
        JSONCustomizeAddon.create(
            configuration={"indent": 8, "sort": 1, "style": "spaces"},
        )
        # This is not needed in real life as installation will happen
        # in a different request so local caching does not apply
        self.component.drop_addons_cache()

        self.asset_customize("        ")

    def test_customize_tabs(self) -> None:
        JSONCustomizeAddon.create(
            component=self.component,
            configuration={"indent": 8, "sort": 1, "style": "tabs"},
        )
        self.asset_customize("\t\t\t\t\t\t\t\t")


class XMLAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_xliff("complex")

    def test_customize_self_closing_tags(self) -> None:
        XMLCustomizeAddon.create(
            component=self.component, configuration={"closing_tags": False}
        )

        rev = self.component.repository.last_revision
        self.edit_unit("Thank you for using Weblate", "Děkujeme, že používáte Weblate")
        self.get_translation().commit_pending("test", None)
        self.assertNotEqual(rev, self.component.repository.last_revision)

        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("<target/>", commit)

    def test_customize_closing_tags(self) -> None:
        XMLCustomizeAddon.create(
            component=self.component, configuration={"closing_tags": True}
        )

        rev = self.component.repository.last_revision
        self.edit_unit("Thank you for using Weblate", "Děkujeme, že používáte Weblate")
        self.get_translation().commit_pending("test", None)
        self.assertNotEqual(rev, self.component.repository.last_revision)

        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("<target></target>", commit)


class YAMLAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_yaml()

    def test_customize(self) -> None:
        if not YAMLCustomizeAddon.can_install(self.component, None):
            raise SkipTest("json dump configuration not supported")
        YAMLCustomizeAddon.create(
            component=self.component,
            configuration={"indent": 8, "wrap": 1000, "line_break": "dos"},
        )
        rev = self.component.repository.last_revision
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.get_translation().commit_pending("test", None)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("        try:", commit)
        self.assertIn("cs.yml", commit)
        with open(self.get_translation().get_filename(), "rb") as handle:
            self.assertIn(b"\r\n", handle.read())


class ViewTests(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.make_manager()

    def test_list(self) -> None:
        response = self.client.get(reverse("addons", kwargs=self.kw_component))
        self.assertContains(response, "Generate MO files")

    def test_addon_logs(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.gettext.authors"},
            follow=True,
        )
        addon = self.component.addon_set.all()[0]
        response = self.client.get(reverse("addon-logs", kwargs={"pk": addon.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "addons/addon_logs.html")
        self.assertEqual(response.context["instance"], addon)

    def test_addon_logs_without_authentication(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.gettext.authors"},
            follow=True,
        )
        addon = self.component.addon_set.all()[0]

        self.client.logout()
        response = self.client.get(reverse("addon-logs", kwargs={"pk": addon.pk}))
        self.assertEqual(response.status_code, 403)

    def test_add_simple(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.gettext.authors"},
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")

    def test_add_simple_project_addon(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_project_path),
            {"name": "weblate.consistency.languages"},
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")

    def test_add_simple_site_wide_addon(self) -> None:
        response = self.client.post(
            reverse("manage-addons"),
            {"name": "weblate.consistency.languages"},
            follow=True,
        )
        self.assertEqual(response.status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("manage-addons"),
            {"name": "weblate.consistency.languages"},
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")

    def test_add_invalid(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "invalid"},
            follow=True,
        )
        self.assertContains(response, "Invalid add-on name:")

    def test_add_config(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.generate.generate"},
            follow=True,
        )
        self.assertContains(response, "Configure add-on")
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.generate.generate",
                "form": "1",
                "filename": "stats/{{ language_code }}.json",
                "template": '{"code":"{{ language_code }}"}',
            },
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")

    def test_add_config_site_wide_addon(self) -> None:
        response = self.client.post(
            reverse("manage-addons"),
            {"name": "weblate.generate.generate"},
            follow=True,
        )
        self.assertEqual(response.status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("manage-addons"),
            {"name": "weblate.generate.generate"},
            follow=True,
        )
        self.assertContains(response, "Configure add-on")
        response = self.client.post(
            reverse("manage-addons"),
            {
                "name": "weblate.generate.generate",
                "form": "1",
                "filename": "stats/{{ language_code }}.json",
                "template": '{"code":"{{ language_code }}"}',
            },
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")

    def test_add_pseudolocale(self) -> None:
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.generate.pseudolocale"},
            follow=True,
        )
        self.assertContains(response, "Configure add-on")
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.generate.pseudolocale",
                "form": "1",
                "source": self.component.source_translation.pk,
                "target": self.component.translation_set.get(language__code="cs").pk,
            },
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")

    def test_edit_config(self) -> None:
        self.test_add_config()
        addon = self.component.addon_set.all()[0]
        response = self.client.get(addon.get_absolute_url())
        self.assertContains(response, "Configure add-on")
        response = self.client.post(addon.get_absolute_url())
        self.assertContains(response, "Configure add-on")
        self.assertContains(response, "This field is required")

    def test_delete(self) -> None:
        addon = SourceEditAddon.create(component=self.component)
        response = self.client.post(
            addon.instance.get_absolute_url(), {"delete": "1"}, follow=True
        )
        self.assertContains(response, "No add-ons currently installed")


class PropertiesAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_java()

    def test_sort(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.assertTrue(PropertiesSortAddon.can_install(self.component, None))
        PropertiesSortAddon.create(component=self.component)
        self.get_translation().commit_pending("test", None)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("java/swing_messages_cs.properties", commit)

    def test_cleanup(self) -> None:
        self.assertTrue(CleanupAddon.can_install(self.component, None))
        init_rev = self.component.repository.last_revision
        addon = CleanupAddon.create(component=self.component)
        self.assertNotEqual(init_rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False, False)
        self.assertEqual(rev, self.component.repository.last_revision)
        addon.post_update(self.component, "", False, False)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("java/swing_messages_cs.properties", commit)
        self.component.do_reset()
        self.assertNotEqual(init_rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("java/swing_messages_cs.properties", commit)
        self.assertIn("-state=Stale", commit)


class CommandTest(ViewTestCase):
    """Test for management commands."""

    def test_list_addons(self) -> None:
        output = StringIO()
        call_command("list_addons", stdout=output)
        self.assertIn("msgmerge", output.getvalue())

    def test_install_not_supported(self) -> None:
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--addon",
            "weblate.flags.same_edit",
            stdout=output,
            stderr=output,
        )
        self.assertIn("Can not install on Test/Test", output.getvalue())

    def test_install_no_form(self) -> None:
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--addon",
            "weblate.gettext.authors",
            stdout=output,
            stderr=output,
        )
        self.assertIn("Successfully installed on Test/Test", output.getvalue())

    def test_install_missing_form(self) -> None:
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--addon",
            "weblate.gettext.mo",
            stdout=output,
            stderr=output,
        )
        self.assertIn("Successfully installed on Test/Test", output.getvalue())

    def test_install_form(self) -> None:
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--addon",
            "weblate.gettext.customize",
            "--configuration",
            '{"width":77}',
            stdout=output,
            stderr=output,
        )
        self.assertIn("Successfully installed on Test/Test", output.getvalue())
        # Test when component is None
        addon_count = Addon.objects.filter_sitewide()
        self.assertEqual(addon_count.count(), 0)
        addon = Addon.objects.get(component=self.component)
        self.assertEqual(addon.configuration, {"width": 77})
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--addon",
            "weblate.gettext.customize",
            "--configuration",
            '{"width":-1}',
            stdout=output,
            stderr=output,
        )
        self.assertIn("Already installed on Test/Test", output.getvalue())
        addon = Addon.objects.get(component=self.component)
        self.assertEqual(addon.configuration, {"width": 77})
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--update",
            "--addon",
            "weblate.gettext.customize",
            "--configuration",
            '{"width":-1}',
            stdout=output,
            stderr=output,
        )
        self.assertIn("Successfully updated on Test/Test", output.getvalue())
        addon = Addon.objects.get(component=self.component)
        self.assertEqual(addon.configuration, {"width": -1})

    def test_install_addon_wrong(self) -> None:
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "install_addon",
                "--all",
                "--addon",
                "weblate.gettext.nonexisting",
                "--configuration",
                '{"width":77}',
            )
        with self.assertRaises(CommandError):
            call_command(
                "install_addon",
                "--all",
                "--addon",
                "weblate.gettext.customize",
                "--configuration",
                "{",
            )
        with self.assertRaises(CommandError):
            call_command(
                "install_addon",
                "--all",
                "--addon",
                "weblate.gettext.customize",
                "--configuration",
                "{}",
                stdout=output,
            )
        with self.assertRaises(CommandError):
            call_command(
                "install_addon",
                "--all",
                "--addon",
                "weblate.gettext.customize",
                "--configuration",
                '{"width":-65535}',
                stderr=output,
            )

    def test_install_pseudolocale(self) -> None:
        output = StringIO()
        call_command(
            "install_addon",
            "--all",
            "--addon",
            "weblate.generate.pseudolocale",
            "--configuration",
            json.dumps(
                {
                    "target": self.translation.id,
                    "source": self.component.source_translation.id,
                }
            ),
            stdout=output,
            stderr=output,
        )
        self.assertIn("Successfully installed on Test/Test", output.getvalue())


class DiscoveryTest(ViewTestCase):
    def test_creation(self) -> None:
        link = self.component.get_repo_link_url()
        self.assertEqual(Component.objects.filter(repo=link).count(), 0)
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            addon = DiscoveryAddon.create(
                component=self.component,
                configuration={
                    "file_format": "po",
                    "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
                    "name_template": "{{ component|title }}",
                    "language_regex": "^(?!xx).*$",
                    "base_file_template": "",
                    "remove": True,
                },
            )
        self.assertEqual(Component.objects.filter(repo=link).count(), 3)
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            addon.post_update(self.component, "", False, False)
        self.assertEqual(Component.objects.filter(repo=link).count(), 3)

    def test_form(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        # Missing params
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.discovery.discovery", "form": "1"},
            follow=True,
        )
        self.assertNotContains(response, "Please review and confirm")
        # Wrong params
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.discovery.discovery",
                "name_template": "xxx",
                "form": "1",
            },
            follow=True,
        )
        self.assertContains(response, "Please include component markup")
        # Missing variable
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.discovery.discovery",
                "form": "1",
                "file_format": "po",
                "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.po",
                "name_template": "{{ component|title }}.{{ ext }}",
                "language_regex": "^(?!xx).*$",
                "base_file_template": "",
                "remove": True,
            },
            follow=True,
        )
        self.assertContains(response, "Undefined variable: &quot;ext&quot;")
        # Correct params for confirmation
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.discovery.discovery",
                "form": "1",
                "file_format": "po",
                "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.(?P<ext>po)",
                "name_template": "{{ component|title }}.{{ ext }}",
                "language_regex": "^(?!xx).*$",
                "base_file_template": "",
                "remove": True,
            },
            follow=True,
        )
        self.assertContains(response, "Please review and confirm")
        # Confirmation
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(
                reverse("addons", kwargs=self.kw_component),
                {
                    "name": "weblate.discovery.discovery",
                    "form": "1",
                    "match": r"(?P<component>[^/]*)/(?P<language>[^/]*)\.(?P<ext>po)",
                    "file_format": "po",
                    "name_template": "{{ component|title }}.{{ ext }}",
                    "language_regex": "^(?!xx).*$",
                    "base_file_template": "",
                    "remove": True,
                    "confirm": True,
                },
                follow=True,
            )
        self.assertContains(response, "Installed 1 add-on")


class ScriptsTest(TestAddonMixin, ViewTestCase):
    def test_example_pre(self) -> None:
        self.assertTrue(ExamplePreAddon.can_install(self.component, None))
        translation = self.get_translation()
        addon = ExamplePreAddon.create(component=self.component)
        addon.pre_commit(translation, "")
        self.assertIn(
            os.path.join(
                self.component.full_path, f"po/{translation.language_code}.po"
            ),
            translation.addon_commit_files,
        )


class LanguageConsistencyTest(ViewTestCase):
    CREATE_GLOSSARIES: bool = True

    def test_language_consistency(self) -> None:
        self.component.new_lang = "add"
        self.component.new_base = "po/hello.pot"
        self.component.save()
        self.create_ts(
            name="TS",
            new_lang="add",
            new_base="ts/cs.ts",
            project=self.component.project,
        )
        self.assertEqual(Translation.objects.count(), 10)

        # Installation should make languages consistent
        addon = LangaugeConsistencyAddon.create(component=self.component)
        self.assertEqual(Translation.objects.count(), 12)

        # Add one language
        language = Language.objects.get(code="af")
        self.component.add_new_language(language, None)
        self.assertEqual(
            Translation.objects.filter(
                language=language, component__project=self.component.project
            ).count(),
            3,
        )

        # Trigger post update signal, should do nothing
        addon.post_update(self.component, "", False, False)
        self.assertEqual(Translation.objects.count(), 15)


class GitSquashAddonTest(ViewTestCase):
    def create(self, mode: str, sitewide: bool = False):
        self.assertTrue(GitSquashAddon.can_install(self.component, None))
        component = None if sitewide else self.component
        if sitewide:
            # This is not needed in real life as installation will happen
            # in a different request so local caching does not apply
            self.component.drop_addons_cache()
        return GitSquashAddon.create(
            component=component, configuration={"squash": mode}
        )

    def edit(self) -> None:
        for lang in ("cs", "de"):
            self.change_unit("Nazdar svete!\n", "Hello, world!\n", lang)
            self.component.commit_pending("test", None)
            self.change_unit(
                "Diky za pouziti Weblate.",
                "Thank you for using Weblate.",
                lang,
                user=self.anotheruser,
            )
            self.component.commit_pending("test", None)

    def test_squash(
        self, mode: str = "all", expected: int = 1, sitewide: bool = False
    ) -> None:
        addon = self.create(mode=mode, sitewide=sitewide)
        repo = self.component.repository
        self.assertEqual(repo.count_outgoing(), 0)
        # Test no-op behavior
        addon.post_commit(self.component)
        # Make some changes
        self.edit()
        self.assertEqual(repo.count_outgoing(), expected)

    def test_squash_sitewide(self):
        self.test_squash(sitewide=True)

    def test_languages(self) -> None:
        self.test_squash("language", 2)

    def test_files(self) -> None:
        self.test_squash("file", 2)

    def test_mo(self) -> None:
        GenerateMoAddon.create(component=self.component)
        self.test_squash("file", 3)

    def test_author(self) -> None:
        self.test_squash("author", 2)
        # Add commit which can not be squashed
        self.change_unit("Diky za pouzivani Weblate.", "Thank you for using Weblate.")
        self.component.commit_pending("test", None)
        self.assertEqual(self.component.repository.count_outgoing(), 3)

    def test_commit_message(self) -> None:
        commit_message = "Squashed commit message"
        GitSquashAddon.create(
            component=self.component,
            configuration={"squash": "all", "commit_message": commit_message},
        )

        self.edit()

        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn(commit_message, commit)
        self.assertEqual(self.component.repository.count_outgoing(), 1)

    def test_append_trailers(self) -> None:
        GitSquashAddon.create(
            component=self.component,
            configuration={"squash": "all", "append_trailers": True},
        )

        self.edit()

        commit = self.component.repository.show(self.component.repository.last_revision)

        expected_trailers = (
            "    Translate-URL: http://example.com/projects/test/test/cs/\n"
            "    Translate-URL: http://example.com/projects/test/test/de/\n"
            "    Translation: Test/Test\n"
        )
        self.assertIn(expected_trailers, commit)
        self.assertEqual(self.component.repository.count_outgoing(), 1)


class TestRemoval(ViewTestCase):
    def install(self, sitewide: bool = False):
        self.assertTrue(RemoveComments.can_install(self.component, None))
        self.assertTrue(RemoveSuggestions.can_install(self.component, None))
        return (
            RemoveSuggestions.create(
                component=None if sitewide else self.component,
                configuration={"age": 7},
            ),
            RemoveComments.create(
                component=None if sitewide else self.component,
                configuration={"age": 7},
            ),
        )

    def assert_count(self, comments=0, suggestions=0) -> None:
        self.assertEqual(Comment.objects.count(), comments)
        self.assertEqual(Suggestion.objects.count(), suggestions)

    def test_noop(self) -> None:
        suggestions, comments = self.install()
        suggestions.daily(self.component)
        comments.daily(self.component)
        self.assert_count()

    def add_content(self) -> None:
        unit = self.get_unit()
        unit.comment_set.create(user=None, comment="comment")
        unit.suggestion_set.create(user=None, target="suggestion")

    def test_current(self) -> None:
        suggestions, comments = self.install()
        self.add_content()
        suggestions.daily(self.component)
        comments.daily(self.component)
        self.assert_count(1, 1)

    @staticmethod
    def age_content() -> None:
        old = timezone.now() - timedelta(days=60)
        Comment.objects.all().update(timestamp=old)
        Suggestion.objects.all().update(timestamp=old)

    def test_old(self) -> None:
        suggestions, comments = self.install()
        self.add_content()
        self.age_content()
        suggestions.daily(self.component)
        comments.daily(self.component)
        self.assert_count()

    def test_votes(self) -> None:
        suggestions, comments = self.install()
        self.add_content()
        self.age_content()
        Vote.objects.create(
            user=self.user, suggestion=Suggestion.objects.all()[0], value=1
        )
        suggestions.daily(self.component)
        comments.daily(self.component)
        self.assert_count(suggestions=1)

    def test_daily(self) -> None:
        self.install()
        self.add_content()
        self.age_content()
        daily_addons()
        # Ensure the add-on is executed
        daily_addons(modulo=False)
        self.assert_count()

    def test_daily_sitewide(self) -> None:
        self.install(sitewide=True)
        self.add_content()
        self.age_content()
        daily_addons()
        # Ensure the add-on is executed
        daily_addons(modulo=False)
        self.assert_count()


class AutoTranslateAddonTest(ViewTestCase):
    def test_auto(self) -> None:
        self.assertTrue(AutoTranslateAddon.can_install(self.component, None))
        addon = AutoTranslateAddon.create(
            component=self.component,
            configuration={
                "component": "",
                "filter_type": "todo",
                "auto_source": "mt",
                "engines": [],
                "threshold": 80,
                "mode": "translate",
            },
        )
        addon.component_update(self.component)


class BulkEditAddonTest(ViewTestCase):
    def test_bulk(self) -> None:
        label = self.project.label_set.create(name="test", color="navy")
        self.assertTrue(BulkEditAddon.can_install(self.component, None))
        addon = BulkEditAddon.create(
            component=self.component,
            configuration={
                "q": "state:translated",
                "state": -1,
                "add_labels": ["test"],
                "remove_labels": [],
                "add_flags": "",
                "remove_flags": "",
            },
        )
        addon.component_update(self.component)
        self.assertEqual(label.unit_set.count(), 1)

    def test_create(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        label = self.project.label_set.create(name="test", color="navy")
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {"name": "weblate.flags.bulk"},
            follow=True,
        )
        self.assertContains(response, "Configure add-on")
        response = self.client.post(
            reverse("addons", kwargs=self.kw_component),
            {
                "name": "weblate.flags.bulk",
                "form": "1",
                "q": "state:translated",
                "state": -1,
                "add_labels": [label.pk],
                "remove_labels": [],
                "add_flags": "",
                "remove_flags": "",
            },
            follow=True,
        )
        self.assertContains(response, "Installed 1 add-on")


class CDNJSAddonTest(ViewTestCase):
    def create_component(self):
        return self.create_json_mono()

    @override_settings(LOCALIZE_CDN_URL=None)
    def test_noconfigured(self) -> None:
        self.assertFalse(CDNJSAddon.can_install(self.component, None))

    @tempdir_setting("LOCALIZE_CDN_PATH")
    @override_settings(LOCALIZE_CDN_URL="http://localhost/")
    def test_cdn(self) -> None:
        self.make_manager()
        self.assertTrue(CDNJSAddon.can_install(self.component, None))

        # Install addon
        addon = CDNJSAddon.create(
            component=self.component,
            configuration={
                "threshold": 0,
                "files": "",
                "cookie_name": "django_languages",
                "css_selector": ".l10n",
            },
        )

        # Check generated files
        self.assertTrue(os.path.isdir(addon.cdn_path("")))
        jsname = addon.cdn_path("weblate.js")
        self.assertTrue(os.path.isfile(jsname))

        # Translate some content
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.component.commit_pending("test", None)

        # Check translation files
        with open(jsname) as handle:
            content = handle.read()
            self.assertIn(".l10n", content)
            self.assertIn('"cs"', content)
        self.assertTrue(os.path.isfile(addon.cdn_path("cs.json")))

        # Configuration
        response = self.client.get(addon.instance.get_absolute_url())
        self.assertContains(response, addon.cdn_js_url)

    @tempdir_setting("LOCALIZE_CDN_PATH")
    @override_settings(LOCALIZE_CDN_URL="http://localhost/")
    def test_extract(self) -> None:
        self.make_manager()
        self.assertTrue(CDNJSAddon.can_install(self.component, None))
        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 8
        )

        # Install addon
        CDNJSAddon.create(
            component=self.component,
            configuration={
                "threshold": 0,
                "files": "html/en.html",
                "cookie_name": "django_languages",
                "css_selector": "*",
            },
        )

        # Verify strings
        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 14
        )

    @tempdir_setting("LOCALIZE_CDN_PATH")
    @override_settings(LOCALIZE_CDN_URL="http://localhost/")
    def test_extract_broken(self) -> None:
        self.make_manager()
        self.assertTrue(CDNJSAddon.can_install(self.component, None))
        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 8
        )

        # Install addon
        CDNJSAddon.create(
            component=self.component,
            configuration={
                "threshold": 0,
                "files": "html/missing.html",
                "cookie_name": "django_languages",
                "css_selector": "*",
            },
        )

        # Verify strings
        self.assertEqual(
            Unit.objects.filter(translation__component=self.component).count(), 8
        )
        # The error should be there
        self.assertTrue(self.component.alert_set.filter(name="CDNAddonError").exists())


class SiteWideAddonsTest(ViewTestCase):
    def create_component(self):
        return self.create_java()

    def test_json(self):
        JSONCustomizeAddon.create(
            configuration={"indent": 8, "sort": 1, "style": "spaces"},
        )
        # This is not needed in real life as installation will happen
        # in a different request so local caching does not apply
        self.component.drop_addons_cache()
        rev = self.component.repository.last_revision

        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.get_translation().commit_pending("test", None)

        self.assertNotEqual(rev, self.component.repository.last_revision)


class TasksTest(TestCase):
    def test_cleanup_addon_activity_log(self) -> None:
        cleanup_addon_activity_log()
