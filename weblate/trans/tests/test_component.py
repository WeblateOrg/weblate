# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for translation models."""

from __future__ import annotations

import os
import pathlib
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch

from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db.models import F
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.auth.models import setup_project_groups
from weblate.checks.models import Check
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.exceptions import FileParseError
from weblate.trans.models import (
    Component,
    PendingUnitChange,
    Project,
    Translation,
    Unit,
)
from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.tests.test_views import (
    ComponentTestCase,
    FixtureTestCase,
    ViewTestCase,
)
from weblate.utils.files import remove_tree
from weblate.utils.state import STATE_EMPTY, STATE_READONLY, STATE_TRANSLATED
from weblate.vcs.base import RepositoryError
from weblate.vcs.models import VCS_REGISTRY

HOST_KEY_MISMATCH_ERROR = """remote: @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
remote: @    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @
remote: @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
remote: The fingerprint for the ED25519 key sent by the remote host is
remote: SHA256:iNmxXxZ8bWlHaurIAg+U/F0CnxJ5yEZECKlMeFJcB8E.
remote: Host key for kallithea-scm.org has changed and you have requested strict checking.
remote: Host key verification failed.
"""


class ComponentTest(RepoTestCase):
    """Component object testing."""

    def verify_component(
        self,
        component: Component,
        translations: int,
        lang: str | None = None,
        units: int = 0,
        unit: str = "Hello, world!\n",
        source_units: int | None = None,
    ) -> None:
        if source_units is None:
            source_units = units
        # Validation
        component.full_clean()
        # Correct path
        self.assertTrue(os.path.exists(component.full_path))
        # Count translations
        self.assertEqual(component.translation_set.count(), translations)
        if lang is not None:
            # Grab translation
            translation = component.translation_set.get(language_code=lang)
            # Count units in it
            self.assertEqual(translation.unit_set.count(), units)
            # Check whether unit exists
            if units:
                self.assertTrue(
                    translation.unit_set.filter(source=unit).exists(),
                    msg="Unit not found, all units: {}".format(
                        "\n".join(translation.unit_set.values_list("source", flat=True))
                    ),
                )
            # Verify that units have valid link to source (non-self)
            if lang != component.source_language.code:
                self.assertFalse(
                    translation.unit_set.filter(source_unit_id=F("id")).exists()
                )

        if component.has_template():
            self.assertEqual(component.source_translation.filename, component.template)
        # Count units in the source languaage
        self.assertEqual(component.source_translation.unit_set.count(), units)
        # Count translated units in the source language
        self.assertEqual(
            component.source_translation.unit_set.filter(
                state__gte=STATE_TRANSLATED
            ).count(),
            source_units,
        )
        # Verify that source units have valid link to source
        self.assertFalse(
            component.source_translation.unit_set.exclude(
                source_unit_id=F("id")
            ).exists()
        )

    def test_create(self) -> None:
        component = self.create_component()
        self.verify_component(component, 4, "cs", 4)
        self.assertTrue(os.path.exists(component.full_path))
        unit = Unit.objects.get(
            source="Hello, world!\n", translation__language__code="en"
        )
        self.assertEqual(unit.state, STATE_READONLY)
        self.assertEqual(unit.target, "Hello, world!\n")
        unit = Unit.objects.get(
            source="Hello, world!\n", translation__language__code="cs"
        )
        self.assertEqual(unit.state, STATE_EMPTY)

    def test_create_dot(self) -> None:
        component = self._create_component("po", "./po/*.po")
        self.verify_component(component, 4, "cs", 4)
        self.assertTrue(os.path.exists(component.full_path))
        self.assertEqual("po/*.po", component.filemask)

    def test_create_iphone(self) -> None:
        component = self.create_iphone()
        self.verify_component(component, 2, "cs", 4)

    def test_create_ts(self) -> None:
        component = self.create_ts("-translated")
        self.verify_component(component, 2, "cs", 4)

        unit = Unit.objects.get(
            source__startswith="Orangutan", translation__language_code="cs"
        )
        self.assertTrue(unit.is_plural)
        self.assertFalse(unit.translated)
        self.assertFalse(unit.fuzzy)

        unit = Unit.objects.get(
            source__startswith="Hello", translation__language_code="cs"
        )
        self.assertFalse(unit.is_plural)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assertEqual(unit.target, "Hello, world!\n")

        unit = Unit.objects.get(
            source__startswith="Thank ", translation__language_code="cs"
        )
        self.assertFalse(unit.is_plural)
        self.assertFalse(unit.translated)
        self.assertTrue(unit.fuzzy)
        self.assertEqual(unit.target, "Thanks")

    def test_create_ts_mono(self) -> None:
        component = self.create_ts_mono()
        self.verify_component(component, 2, "cs", 4)

    def test_create_appstore(self) -> None:
        component = self.create_appstore()
        self.verify_component(
            component, 2, "cs", 3, "Weblate - continuous localization"
        )

    def test_create_po_pot(self) -> None:
        component = self._create_component("po", "po/*.po", new_base="po/project.pot")
        self.verify_component(component, 4, "cs", 4)
        unit = Unit.objects.get(
            source="Hello, world!\n", translation__language__code="en"
        )
        self.assertEqual(unit.state, STATE_READONLY)
        self.assertEqual(unit.target, "Hello, world!\n")
        unit = Unit.objects.get(
            source="Hello, world!\n", translation__language__code="cs"
        )
        self.assertEqual(unit.state, STATE_EMPTY)

    def test_create_filtered(self) -> None:
        component = self._create_component("po", "po/*.po", language_regex="^cs$")
        self.verify_component(component, 2, "cs", 4)

    def test_create_po(self) -> None:
        component = self.create_po()
        self.verify_component(component, 4, "cs", 4)

    def test_create_srt(self) -> None:
        component = self.create_srt()
        self.verify_component(component, 2, "cs", 4, "Hello, world!")

    def test_create_po_mercurial(self) -> None:
        component = self.create_po_mercurial()
        self.verify_component(component, 4, "cs", 4)

    def test_create_po_branch(self) -> None:
        component = self.create_po_branch()
        self.verify_component(component, 4, "cs", 4)

    def test_create_po_mercurial_branch(self) -> None:
        component = self.create_po_mercurial_branch()
        self.verify_component(component, 4, "cs", 4)

    def test_create_po_push(self) -> None:
        component = self.create_po_push()
        self.verify_component(component, 4, "cs", 4)

    def test_create_po_svn(self) -> None:
        component = self.create_po_svn()
        self.verify_component(component, 4, "cs", 4)

    def test_create_po_empty(self) -> None:
        component = self.create_po_empty()
        self.verify_component(component, 1, "en", 4)
        unit = Unit.objects.get(source="Hello, world!\n")
        self.assertEqual(unit.state, STATE_READONLY)
        self.assertEqual(unit.target, "Hello, world!\n")

    def test_create_po_link(self) -> None:
        component = self.create_po_link()
        self.assertEqual(
            set(component.translation_set.values_list("language_code", flat=True)),
            {"en", "cs", "de", "it"},
        )
        self.verify_component(component, 4, "cs", 4)

    def test_create_po_mono(self) -> None:
        component = self.create_po_mono()
        self.verify_component(component, 4, "cs", 4)

    def test_create_android(self) -> None:
        component = self.create_android()
        self.verify_component(component, 2, "cs", 4)

    def test_create_android_broken(self) -> None:
        component = self.create_android(suffix="-broken")
        self.verify_component(component, 1, "en", 4)

    def test_create_json(self) -> None:
        component = self.create_json()
        self.verify_component(component, 2, "cs", 4)

    def test_create_json_mono(self) -> None:
        component = self.create_json_mono()
        self.verify_component(component, 2, "cs", 4)

    def test_create_json_nested(self) -> None:
        component = self.create_json_mono(suffix="nested")
        self.verify_component(component, 2, "cs", 4)

    def test_create_json_webextension(self) -> None:
        component = self.create_json_webextension()
        self.verify_component(component, 2, "cs", 4)

    def test_create_json_intermediate(self) -> None:
        component = self.create_json_intermediate()
        # The English one should have source from intermediate
        # Only 3 source units are "translated" here
        self.verify_component(component, 2, "en", 4, "Hello world!\n", source_units=3)
        # For Czech the English source string should be used
        self.verify_component(component, 2, "cs", 4, source_units=3)
        # Verify source strings are loaded from correct file
        translation = component.translation_set.get(language_code="cs")
        self.assertEqual(
            translation.unit_set.get(context="hello").source, "Hello, world!\n"
        )
        self.assertEqual(
            translation.unit_set.get(context="thanks").source,
            "Thank you for using Weblate.",
        )
        # Verify source units
        unit = component.source_translation.unit_set.get(context="hello")
        self.assertEqual(unit.source, "Hello world!\n")
        self.assertEqual(unit.target, "Hello, world!\n")

    def test_component_screenshot_filemask(self) -> None:
        component = self._create_component(
            "json", "intermediate/*.json", screenshot_filemask="screenshots/*.png"
        )
        self.assertEqual(component.screenshot_filemask, "screenshots/*.png")

    def test_switch_json_intermediate(self) -> None:
        component = self._create_component(
            "json",
            "intermediate/*.json",
            "intermediate/dev.json",
            language_regex="^cs$",
        )
        translation = component.translation_set.get(language_code="cs")
        self.assertEqual(
            translation.unit_set.get(context="hello").source, "Hello world!\n"
        )
        self.assertEqual(
            translation.unit_set.get(context="thanks").source,
            "Thanks for using Weblate.",
        )
        component.intermediate = "intermediate/dev.json"
        component.template = "intermediate/en.json"
        component.save()
        translation = component.translation_set.get(language_code="cs")
        self.assertEqual(
            translation.unit_set.get(context="hello").source, "Hello, world!\n"
        )
        self.assertEqual(
            translation.unit_set.get(context="thanks").source,
            "Thank you for using Weblate.",
        )

    def test_create_json_intermediate_empty(self) -> None:
        # This should automatically create empty English file
        component = self.create_json_intermediate_empty()
        # The English one should have source from intermediate and no translated units
        self.verify_component(component, 1, "en", 4, "Hello world!\n", source_units=0)

    def test_create_joomla(self) -> None:
        component = self.create_joomla()
        self.verify_component(component, 3, "cs", 4)

    def test_create_ini(self) -> None:
        component = self.create_ini()
        self.verify_component(component, 2, "cs", 4, "Hello, world!\\n")

    def test_create_tsv_simple(self) -> None:
        component = self._create_component("csv-simple", "tsv/*.txt")
        self.verify_component(component, 2, "cs", 4, "Hello, world!")

    def test_create_tsv_simple_iso(self) -> None:
        component = self._create_component(
            "csv-simple",
            "tsv/*.txt",
            file_format_params={"csv_simple_encoding": "iso-8859-1"},
        )
        self.verify_component(component, 2, "cs", 4, "Hello, world!")

    def test_create_csv(self) -> None:
        component = self.create_csv()
        self.verify_component(component, 2, "cs", 4)

    def test_create_csv_mono(self) -> None:
        component = self.create_csv_mono()
        self.verify_component(component, 2, "cs", 4)

    def test_create_php_mono(self) -> None:
        component = self.create_php_mono()
        self.verify_component(component, 2, "cs", 4)

    def test_create_tsv(self) -> None:
        component = self.create_tsv()
        self.verify_component(component, 2, "cs", 4, "Hello, world!")

    def test_create_java(self) -> None:
        component = self.create_java()
        self.verify_component(component, 3, "cs", 4)

    def test_create_xliff(self) -> None:
        component = self.create_xliff()
        self.verify_component(component, 2, "cs", 4)

    def test_create_xliff_complex(self) -> None:
        component = self.create_xliff("complex")
        self.verify_component(component, 2, "cs", 4)

    def test_create_xliff_mono(self) -> None:
        component = self.create_xliff_mono()
        self.verify_component(component, 2, "cs", 4)

    def test_create_xliff_dph(self) -> None:
        component = self.create_xliff(
            "DPH", source_language=Language.objects.get(code="cs")
        )
        self.verify_component(component, 2, "en", 9, "DPH")

    def test_create_xliff_empty(self) -> None:
        component = self.create_xliff(
            "EMPTY", source_language=Language.objects.get(code="cs")
        )
        self.verify_component(component, 2, "en", 6, "DPH")

    def test_create_xliff_resname(self) -> None:
        component = self.create_xliff(
            "Resname", source_language=Language.objects.get(code="cs")
        )
        self.verify_component(component, 2, "en", 2, "Hi")

    def test_create_xliff_only_resname(self) -> None:
        component = self.create_xliff("only-resname")
        self.verify_component(component, 2, "cs", 4)

    def test_create_resx(self) -> None:
        component = self.create_resx()
        self.verify_component(component, 2, "cs", 4)

    def test_create_yaml(self) -> None:
        component = self.create_yaml()
        self.verify_component(component, 2, "cs", 4)

    def test_create_ruby_yaml(self) -> None:
        component = self.create_ruby_yaml()
        self.verify_component(component, 2, "cs", 4)

    def test_create_dtd(self) -> None:
        component = self.create_dtd()
        self.verify_component(component, 2, "cs", 4)

    def test_create_html(self) -> None:
        component = self.create_html()
        self.verify_component(component, 2, "cs", 4, unit="Hello, world!")

    def test_create_idml(self) -> None:
        component = self.create_idml()
        self.verify_component(
            component,
            1,
            "en",
            5,
            unit="""<g id="0"><g id="1">THE HEADLINE HERE</g></g>""",
        )

    def test_create_odt(self) -> None:
        component = self.create_odt()
        self.verify_component(component, 2, "cs", 4, unit="Hello, world!")

    def test_create_winrc(self) -> None:
        component = self.create_winrc()
        self.verify_component(component, 2, "cs-CZ", 4)

    def test_create_tbx(self) -> None:
        component = self.create_tbx()
        self.verify_component(component, 2, "cs", 5, unit="address bar")

        translation = component.translation_set.get(language_code="cs")
        unit = translation.unit_set.get(source="application")
        self.assertEqual(
            unit.source_unit.explanation,
            "a computer program designed for a specific task or use",
        )

    def test_link(self) -> None:
        component = self.create_link()
        self.verify_component(component, 4, "cs", 4)

    def test_flags(self) -> None:
        """Translation flags validation."""
        component = self.create_component()
        component.full_clean()

        component.check_flags = "ignore-inconsistent"
        component.full_clean()

        component.check_flags = "rst-text,ignore-inconsistent"
        component.full_clean()

        component.check_flags = "nonsense"
        with self.assertRaisesMessage(
            ValidationError,
            'Invalid translation flag: "nonsense"',
        ):
            component.full_clean()

        component.check_flags = "rst-text,ignore-nonsense"
        with self.assertRaisesMessage(
            ValidationError,
            'Invalid translation flag: "ignore-nonsense"',
        ):
            component.full_clean()

    def test_lang_code_template(self) -> None:
        component = Component(project=Project())
        component.filemask = "Solution/Project/Resources.*.resx"
        component.template = "Solution/Project/Resources.resx"
        self.assertEqual(
            component.get_lang_code("Solution/Project/Resources.resx"), "en"
        )

    def test_switch_branch(self) -> None:
        component = self.create_po()
        # Switch to translation branch
        self.verify_component(component, 4, "cs", 4)
        component.branch = "translations"
        component.filemask = "translations/*.po"
        component.clean()
        component.save()
        self.verify_component(component, 4, "cs", 4)
        # Switch back to main branch
        component.branch = "main"
        component.filemask = "po/*.po"
        component.clean()
        component.save()
        self.verify_component(component, 4, "cs", 4)

    def test_switch_branch_mercurial(self) -> None:
        component = self.create_po_mercurial()
        # Switch to translation branch
        self.verify_component(component, 4, "cs", 4)
        component.branch = "translations"
        component.filemask = "translations/*.po"
        component.clean()
        component.save()
        self.verify_component(component, 4, "cs", 4)
        # Switch back to default branch
        component.branch = "default"
        component.filemask = "po/*.po"
        component.clean()
        component.save()
        self.verify_component(component, 4, "cs", 4)

    def test_update_checks(self) -> None:
        """Setting of check_flags changes checks for related units."""
        component = self.create_component()
        self.assertEqual(Check.objects.count(), 3)
        check = Check.objects.all()[0]
        component.check_flags = f"ignore-{check.name}"
        component.save()
        self.assertEqual(Check.objects.count(), 0)

    def test_create_symlinks(self):
        component = self._create_component("po", "po-brokenlink/*.po")
        # - xx should not be present as it is a symlink to existing translation
        # - fr should not be present as it is a symlink out of tree
        self.assertEqual(
            set(component.translation_set.values_list("language_code", flat=True)),
            {"en", "cs", "de", "it"},
        )
        self.verify_component(component, 4, "cs", 4)

    @override_settings(
        GITHUB_CREDENTIALS={
            "api.github.com": {
                "username": "test",
                "token": "token",
            }
        }
    )
    def test_vcs_validation(self) -> None:
        component = self.create_po_push()

        # force reload VCS list to include github
        del VCS_REGISTRY.data

        component.vcs = "github"

        # check push branch cannot be empty when push URL is set
        component.push_branch = ""
        with (
            patch("weblate.trans.models.Component.sync_git_repo", return_value=None),
            self.assertRaises(ValidationError) as cm,
        ):
            component.clean()
        self.assertIn(
            "Push branch cannot be empty when using pull/merge requests",
            str(cm.exception),
        )

        # check push and pull branch cannot be the same when push URL is set
        component.push_branch = "main"
        with (
            patch("weblate.trans.models.Component.sync_git_repo", return_value=None),
            self.assertRaises(ValidationError) as cm,
        ):
            component.clean()
        self.assertIn(
            "Pull and push branches cannot be the same when using pull/merge requests",
            str(cm.exception),
        )

        # valid settings
        component.push_branch = "branch"
        component.clean()

    def test_invalid_git_branch_validation(self) -> None:
        component = self.create_po()
        component.branch = "--orphan"

        with (
            patch("weblate.trans.models.Component.sync_git_repo", return_value=None),
            self.assertRaises(ValidationError) as cm,
        ):
            component.clean()

        self.assertIn("Invalid repository branch", str(cm.exception))

    def test_invalid_git_push_branch_validation(self) -> None:
        component = self.create_po_push()
        component.push_branch = "--orphan"

        with (
            patch("weblate.trans.models.Component.sync_git_repo", return_value=None),
            self.assertRaises(ValidationError) as cm,
        ):
            component.clean()

        self.assertIn("Invalid push branch", str(cm.exception))

    def _test_maintenance(self, component: Component) -> None:
        self.verify_component(component, 4, "cs", 4)
        with component.repository.lock:
            component.repository.maintenance()
        component.create_translations_immediate(force=True)
        self.verify_component(component, 4, "cs", 4)
        with component.repository.lock:
            component.repository.cleanup()
        component.create_translations_immediate(force=True)
        self.verify_component(component, 4, "cs", 4)

    def test_maintenance_po(self):
        component = self.create_po()
        self._test_maintenance(component)

    def test_maintenance_po_branch(self):
        component = self.create_po_branch()
        self._test_maintenance(component)

    def test_maintenance_po_mercurial(self):
        component = self.create_po_mercurial()
        self._test_maintenance(component)

    def test_maintenance_po_mercurial_branch(self):
        component = self.create_po_mercurial_branch()
        self._test_maintenance(component)


class AutoAddonTest(RepoTestCase):
    CREATE_GLOSSARIES = True

    @override_settings(
        DEFAULT_ADDONS={
            # Invalid addon name
            "weblate.invalid.invalid": {},
            # Duplicate (installed by file format)
            "weblate.flags.same_edit": {},
            # Not compatible
            "weblate.gettext.mo": {},
            # Missing params
            "weblate.removal.comments": {},
            # Correct
            "weblate.autotranslate.autotranslate": {
                "mode": "suggest",
                "q": "state:<translated",
                "auto_source": "mt",
                "component": "",
                "engines": ["weblate-translation-memory"],
                "threshold": "80",
            },
        }
    )
    def test_create_autoaddon(self) -> None:
        self.configure_mt()
        component = self.create_idml()
        self.assertEqual(
            set(component.addon_set.values_list("name", flat=True)),
            {
                "weblate.flags.same_edit",
                "weblate.autotranslate.autotranslate",
                "weblate.cleanup.generic",
            },
        )

    @override_settings(
        DEFAULT_ADDONS={
            "weblate.gettext.msgmerge": {},
        }
    )
    def test_create_autoaddon_msgmerge(self) -> None:
        component = self.create_po(new_base="po/project.pot")
        self.assertEqual(
            set(component.addon_set.values_list("name", flat=True)),
            {"weblate.gettext.msgmerge"},
        )
        self.assertEqual(component.count_repo_outgoing, 1)


class ComponentDeleteTest(RepoTestCase):
    """Component object deleting testing."""

    def test_delete(self) -> None:
        component = self.create_component()
        self.assertTrue(os.path.exists(component.full_path))
        component.delete()
        self.assertFalse(os.path.exists(component.full_path))
        self.assertEqual(0, Component.objects.count())

    def test_delete_link(self) -> None:
        component = self.create_link()
        main_project = Component.objects.get(slug="test")
        self.assertTrue(os.path.exists(main_project.full_path))
        component.delete()
        self.assertTrue(os.path.exists(main_project.full_path))

    def test_delete_all(self) -> None:
        component = self.create_component()
        self.assertTrue(os.path.exists(component.full_path))
        Component.objects.all().delete()
        self.assertFalse(os.path.exists(component.full_path))

    def test_delete_with_checks(self) -> None:
        """Test deleting of component with checks works."""
        component = self.create_component()
        # Introduce missing source string check. This can happen when adding new check
        # on upgrade or similar situation.
        unit = Unit.objects.filter(check__isnull=False)[0].source_unit
        unit.source = "Test..."
        unit.save(update_fields=["source"])
        self.assertEqual(unit.check_set.filter(name="ellipsis").delete()[0], 1)
        component.delete()


class ComponentChangeTest(RepoTestCase):
    """Component object change testing."""

    def test_rename(self) -> None:
        link_component = self.create_link()
        self.assertIsNotNone(link_component.linked_component)
        component = cast("Component", link_component.linked_component)
        self.assertTrue(Component.objects.filter(repo="weblate://test/test").exists())

        old_path = component.full_path
        self.assertTrue(os.path.exists(old_path))
        self.assertTrue(
            os.path.exists(
                component.translation_set.get(language_code="cs").get_filename()
            )
        )
        component.slug = "changed"
        component.save()
        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(component.full_path))
        self.assertTrue(
            os.path.exists(
                component.translation_set.get(language_code="cs").get_filename()
            )
        )

        self.assertTrue(
            Component.objects.filter(repo="weblate://test/changed").exists()
        )
        self.assertFalse(Component.objects.filter(repo="weblate://test/test").exists())

    def test_unlink_clean(self) -> None:
        """Test changing linked component to real repo based one."""
        component = self.create_link()
        component.repo = cast("Component", component.linked_component).repo
        component.clean()
        component.save()

    def test_unlink(self) -> None:
        """Test changing linked component to real repo based one."""
        component = self.create_link()
        component.repo = cast("Component", component.linked_component).repo
        component.save()

    def test_change_project(self) -> None:
        component = self.create_component()

        # Check current path exists
        old_path = component.full_path
        self.assertTrue(os.path.exists(old_path))

        # Crete target project
        second = Project.objects.create(
            name="Test2", slug="test2", web="https://weblate.org/"
        )

        # Move component
        component.project = second
        component.save()

        # Check new path exists
        new_path = component.full_path
        self.assertTrue(os.path.exists(new_path))

        # Check paths differ
        self.assertNotEqual(old_path, new_path)

    def test_change_to_mono(self) -> None:
        """Test switching to monolingual format on the fly."""
        component = self._create_component("po", "po-mono/*.po")
        self.assertEqual(component.translation_set.count(), 4)
        component.file_format = "po-mono"
        component.template = "po-mono/en.po"
        component.save()
        self.assertEqual(component.translation_set.count(), 4)

    def test_autolock(self) -> None:
        component = self.create_component()
        start = component.change_set.count()

        component.add_alert("MergeFailure")
        self.assertTrue(component.locked)
        # Locked event, alert added
        self.assertEqual(component.change_set.count() - start, 2)

        change = component.change_set.get(action=ActionEvents.LOCK)
        self.assertEqual(change.details, {"auto": True})
        self.assertEqual(change.get_action_display(), "Component locked")
        self.assertEqual(
            change.get_details_display(),
            "The component was automatically locked because of an alert.",
        )

        component.add_alert("UpdateFailure")
        self.assertTrue(component.locked)
        # No other locked event, alert added
        self.assertEqual(component.change_set.count() - start, 3)

        component.delete_alert("UpdateFailure")
        self.assertTrue(component.locked)
        # No other locked event
        self.assertEqual(component.change_set.count() - start, 3)

        component.delete_alert("MergeFailure")
        self.assertFalse(component.locked)
        # Unlocked event
        self.assertEqual(component.change_set.count() - start, 4)

    def test_do_lock_rolls_back_when_change_save_fails(self) -> None:
        component = self.create_component()

        with (
            self.assertRaisesMessage(RuntimeError, "change save failed"),
            patch(
                "weblate.trans.models.component.Change.save",
                autospec=True,
                side_effect=RuntimeError("change save failed"),
            ),
        ):
            component.do_lock(user=None)

        component.refresh_from_db()
        self.assertFalse(component.locked)
        self.assertFalse(component.change_set.filter(action=ActionEvents.LOCK).exists())

    def test_linked_autolock_uses_main_setting(self) -> None:
        component = self.create_po(name="main-autolock")
        self.component = component
        self.project = component.project
        linked_component = self.create_link_existing(
            name="Linked autolock", slug="linked-autolock"
        )
        component.auto_lock_error = False
        component.save(update_fields=["auto_lock_error"])
        linked_component.auto_lock_error = True
        linked_component.save(update_fields=["auto_lock_error"])

        component.add_alert("MergeFailure")

        component.refresh_from_db()
        linked_component.refresh_from_db()
        self.assertFalse(component.locked)
        self.assertFalse(linked_component.locked)

    def test_linked_push_if_needed_uses_main_setting(self) -> None:
        self.component = self.create_po(name="main-push")
        self.project = self.component.project
        linked_component = self.create_link_existing(
            name="Linked push", slug="linked-push"
        )
        self.component.push_on_commit = True
        self.component.save(update_fields=["push_on_commit"])
        linked_component.push_on_commit = False
        linked_component.save(update_fields=["push_on_commit"])
        linked_component = Component.objects.get(pk=linked_component.pk)

        with (
            patch.object(Component, "can_push", return_value=True),
            patch.object(Component, "repo_needs_push", return_value=True),
            patch.object(Component, "do_push") as mock_do_push,
        ):
            linked_component.push_if_needed(do_update=False)

        mock_do_push.assert_called_once_with(None, force_commit=False, do_update=False)

    def test_linked_autolock_locks_child_from_main_setting(self) -> None:
        component = self.create_po(name="main-autolock-child")
        self.component = component
        self.project = component.project
        linked_component = self.create_link_existing(
            name="Linked autolock child", slug="linked-autolock-child"
        )
        component.auto_lock_error = True
        component.save(update_fields=["auto_lock_error"])
        linked_component.auto_lock_error = False
        linked_component.save(update_fields=["auto_lock_error"])

        component.add_alert("MergeFailure")

        component.refresh_from_db()
        linked_component.refresh_from_db()
        self.assertTrue(component.locked)
        self.assertTrue(linked_component.locked)


class ComponentValidationTest(RepoTestCase):
    """Component object validation testing."""

    def setUp(self) -> None:
        super().setUp()
        self.component = self.create_component()
        # Ensure we have correct component
        self.component.full_clean()

    def test_commit_message(self) -> None:
        """Invalid commit message."""
        self.component.commit_message = "{% if %}"
        with self.assertRaises(ValidationError):
            self.component.full_clean()

    def test_filemask(self) -> None:
        """Invalid mask."""
        self.component.filemask = "foo/x.po"
        with self.assertRaisesMessage(
            ValidationError, "File mask does not contain * as a language placeholder!"
        ):
            self.component.full_clean()

    def test_screenshot_filemask(self) -> None:
        """Invalid screenshot filemask."""
        self.component.screenshot_filemask = "foo/x.png"
        with self.assertRaisesMessage(
            ValidationError, "File mask does not contain * as a language placeholder!"
        ):
            self.component.full_clean()

    def test_no_matches(self) -> None:
        """Not matching mask."""
        self.component.filemask = "foo/*.po"
        with self.assertRaisesMessage(
            ValidationError, "The file mask did not match any files."
        ):
            self.component.full_clean()

    def test_fileformat(self) -> None:
        """Unknown file format."""
        self.component.file_format = "i18next"
        self.component.filemask = "invalid/*.invalid"
        with self.assertRaisesMessage(
            ValidationError, "Could not parse 2 matched files."
        ):
            self.component.full_clean()

    def test_repoweb(self) -> None:
        """Invalid repoweb format."""
        self.component.repoweb = "http://{{foo}}/{{bar}}/%72"
        with self.assertRaisesMessage(ValidationError, 'Undefined variable: "foo"'):
            self.component.full_clean()
        self.component.repoweb = "http://{{ component_name }}/{{ filename }}/%72"
        with self.assertRaisesMessage(ValidationError, "Enter a valid URL"):
            self.component.full_clean()
        self.component.repoweb = (
            "http://example.com/{{ component_name }}/{{ filename }}/%72"
        )
        self.assertIsNone(self.component.full_clean())
        self.component.repoweb = ""

    def test_link_incomplete(self) -> None:
        """Incomplete link."""
        self.component.repo = "weblate://foo"
        self.component.push = ""
        with self.assertRaisesMessage(
            ValidationError,
            "Invalid link to a Weblate project, use weblate://project/component.",
        ):
            self.component.full_clean()

    def test_link_nonexisting(self) -> None:
        """Link to non existing project."""
        self.component.repo = "weblate://foo/bar"
        self.component.push = ""
        with self.assertRaisesMessage(
            ValidationError,
            "Invalid link to a Weblate project, use weblate://project/component.",
        ):
            self.component.full_clean()

    def test_link_self(self) -> None:
        """Link pointing to self."""
        self.component.repo = "weblate://test/test"
        self.component.push = ""
        with self.assertRaisesMessage(
            ValidationError,
            "Invalid link to a Weblate project, cannot link it to itself!",
        ):
            self.component.full_clean()

    def test_private_repo_rejected(self) -> None:
        self.component.repo = "https://private.example/repo.git"
        with (
            patch("weblate.trans.models.component.Component.sync_git_repo"),
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
            self.assertRaises(ValidationError) as error,
        ):
            self.component.full_clean()
        self.assertIn("internal or non-public address", str(error.exception))

    def test_private_push_rejected(self) -> None:
        self.component.push = "https://private.example/repo.git"
        with (
            patch("weblate.trans.models.component.Component.sync_git_repo"),
            patch(
                "weblate.utils.outbound.socket.getaddrinfo",
                return_value=[(0, 0, 0, "", ("127.0.0.1", 443))],
            ),
            self.assertRaises(ValidationError) as error,
        ):
            self.component.full_clean()
        self.assertIn("internal or non-public address", str(error.exception))

    def test_validation_mono(self) -> None:
        self.component.project.delete()
        project = self.create_po_mono()
        # Correct project
        project.full_clean()
        # Not existing file
        project.template = "not-existing"
        with self.assertRaisesMessage(ValidationError, "File does not exist."):
            project.full_clean()

    def test_validation_language_re(self) -> None:
        self.component.language_regex = "[-"
        with self.assertRaises(ValidationError):
            self.component.full_clean()

    def test_validation_language_re_timeout(self) -> None:
        with (
            patch(
                "weblate.trans.models.component.regex_match",
                side_effect=TimeoutError,
            ),
            self.assertRaisesMessage(
                ValidationError,
                "The regular expression is too complex and took too long to evaluate.",
            ),
        ):
            self.component.full_clean()

    def test_validation_newlang(self) -> None:
        self.component.new_base = "po/project.pot"
        self.component.save()

        self.component.full_clean()

        self.component.new_lang = "add"
        self.component.save()

        # Check that it doesn't warn about not supported format
        self.component.full_clean()

        self.component.file_format = "po"
        self.component.save()

        # Clean class cache
        del self.component.__dict__["file_format"]

        # With correct format it should validate
        self.component.full_clean()

    def test_lang_code(self) -> None:
        project = Project(language_aliases="xx:cs")
        component = Component(project=project)
        component.filemask = "Solution/Project/Resources.*.resx"
        # Pure extraction
        self.assertEqual(
            component.get_lang_code("Solution/Project/Resources.es-mx.resx"), "es-mx"
        )
        # No match
        self.assertEqual(component.get_lang_code("Solution/Project/Resources.resx"), "")
        # Language aliases
        self.assertEqual(
            component.get_lang_code("Solution/Project/Resources.xx.resx"), "xx"
        )
        self.assertEqual(component.get_language_alias("xx"), "cs")
        with self.assertRaisesMessage(
            ValidationError,
            "The language code for "
            '"Solution/Project/Resources.resx"'
            " is empty, please check the file mask.",
        ):
            component.clean_lang_codes(
                [
                    "Solution/Project/Resources.resx",
                    "Solution/Project/Resources.de.resx",
                    "Solution/Project/Resources.es.resx",
                    "Solution/Project/Resources.es-mx.resx",
                    "Solution/Project/Resources.fr.resx",
                    "Solution/Project/Resources.fr-fr.resx",
                ]
            )

    def test_lang_code_double(self) -> None:
        component = Component(project=Project())
        component.filemask = "path/*/resources/MessagesBundle_*.properties"
        self.assertEqual(
            component.get_lang_code(
                "path/pt/resources/MessagesBundle_pt_BR.properties"
            ),
            "pt_BR",
        )
        self.assertEqual(
            component.get_lang_code("path/el/resources/MessagesBundle_el.properties"),
            "el",
        )

    def test_lang_code_plus(self) -> None:
        component = Component(project=Project())
        component.filemask = "po/*/pages/C_and_C++.po"
        self.assertEqual(
            component.get_lang_code("po/cs/pages/C_and_C++.po"),
            "cs",
        )


class ComponentErrorTest(RepoTestCase):
    """Test for error handling."""

    def setUp(self) -> None:
        super().setUp()
        self.component = self.create_ts_mono()
        # Change to invalid push URL
        self.component.repo = "file:/dev/null"
        self.component.push = "file:/dev/null"
        self.component.save()

    def test_failed_update(self) -> None:
        self.assertFalse(self.component.do_update())

    def test_failed_update_remote(self) -> None:
        self.assertFalse(self.component.update_remote_branch())

    def test_failed_push(self) -> None:
        testfile = os.path.join(self.component.full_path, "README.md")
        with open(testfile, "a", encoding="utf-8") as handle:
            handle.write("CHANGE")
        with self.component.repository.lock:
            self.component.repository.commit("test", files=["README.md"])
        self.assertFalse(self.component.do_push(None))

    def test_failed_reset(self) -> None:
        # Corrupt Git database so that reset fails
        remove_tree(os.path.join(self.component.full_path, ".git", "objects", "pack"))
        self.component.repository.clean_revision_cache()
        self.assertFalse(self.component.do_reset(None))

    def test_invalid_templatename(self) -> None:
        self.component.template = "foo.bar"
        self.component.drop_template_store_cache()

        with self.assertRaises(FileParseError):
            # pylint: disable-next=pointless-statement
            self.component.template_store  # noqa: B018

        with self.assertRaises(ValidationError):
            self.component.clean()

    def test_invalid_filename(self) -> None:
        translation = self.component.translation_set.get(language_code="cs")
        translation.filename = "foo.bar"
        with self.assertRaises(FileParseError):
            # pylint: disable-next=pointless-statement
            translation.store  # noqa: B018
        with self.assertRaises(ValidationError):
            translation.clean()

    def test_invalid_storage(self) -> None:
        testfile = os.path.join(self.component.full_path, "ts-mono", "cs.ts")
        with open(testfile, "a", encoding="utf-8") as handle:
            handle.write("CHANGE")
        translation = self.component.translation_set.get(language_code="cs")
        with self.assertRaises(FileParseError):
            # pylint: disable-next=pointless-statement
            translation.store  # noqa: B018
        with self.assertRaises(ValidationError):
            translation.clean()

    def test_invalid_template_storage(self) -> None:
        testfile = os.path.join(self.component.full_path, "ts-mono", "en.ts")
        with open(testfile, "a", encoding="utf-8") as handle:
            handle.write("CHANGE")
        self.component.drop_template_store_cache()

        with self.assertRaises(FileParseError):
            # pylint: disable-next=pointless-statement
            self.component.template_store  # noqa: B018
        with self.assertRaises(ValidationError):
            self.component.clean()

    def test_change_source_language(self) -> None:
        self.component.source_language = Language.objects.get(code="cs")
        with self.assertRaises(ValidationError):
            self.component.clean()


class ResetReapplyMissingTranslationFileTest(ComponentTestCase):
    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def setUp(self) -> None:
        super().setUp()
        self.de_translation = self.ensure_translation("de")
        self.local_missing_translation_contents: dict[int, bytes] = {}

    def ensure_translation(self, language_code: str) -> Translation:
        language = Language.objects.get(code=language_code)
        if not self.component.translation_set.filter(language=language).exists():
            self.assertIsNotNone(
                self.component.add_new_language(
                    language, self.get_request(), show_messages=False
                )
            )
        return self.component.translation_set.get(language=language)

    def prepare_missing_translation_file(
        self,
        translation: Translation,
        *,
        target: str | None = None,
        commit_to_remote: bool = False,
    ) -> None:
        if target is not None:
            self.change_unit(target, translation=translation)

        filename = cast("str", translation.get_filename())
        with translation.component.repository.lock:
            if commit_to_remote:
                self.local_missing_translation_contents[translation.pk] = pathlib.Path(
                    filename
                ).read_bytes()
                translation.component.repository.remove(
                    [translation.filename],
                    f"Remove {translation.language.name} translation",
                )
                translation.component.repository.push(translation.component.push_branch)
            else:
                pathlib.Path(filename).unlink(missing_ok=True)

    def restore_local_missing_translation_files(
        self, *translations: Translation
    ) -> None:
        with self.component.repository.lock:
            for translation in translations:
                filename = cast("str", translation.get_filename())
                pathlib.Path(filename).write_bytes(
                    self.local_missing_translation_contents[translation.pk]
                )
                translation.component.repository.execute(
                    ["add", "--force", "--", translation.filename]
                )

    def test_reset_keep_recreates_missing_translation_file(self) -> None:
        self.prepare_missing_translation_file(
            self.de_translation,
            target="Hallo Welt!\n",
            commit_to_remote=True,
        )
        self.restore_local_missing_translation_files(self.de_translation)
        self.assertTrue(os.path.exists(cast("str", self.de_translation.get_filename())))

        self.assertTrue(self.component.do_reset(self.get_request(), keep_changes=True))

        self.de_translation.refresh_from_db()
        self.assertTrue(os.path.exists(cast("str", self.de_translation.get_filename())))
        self.assertFalse(
            PendingUnitChange.objects.filter(
                unit__translation=self.de_translation
            ).exists()
        )
        self.assertEqual(
            self.get_unit(language="de", translation=self.de_translation).target,
            "Hallo Welt!\n",
        )

    def test_reset_keep_recreates_missing_translation_file_for_vcs_user(self) -> None:
        self.prepare_missing_translation_file(
            self.de_translation,
            target="Hallo Welt!\n",
            commit_to_remote=True,
        )
        self.restore_local_missing_translation_files(self.de_translation)
        self.project.access_control = Project.ACCESS_PROTECTED
        setup_project_groups(self, self.project)
        self.component.new_lang = "contact"
        self.component.save(update_fields=["new_lang"])
        self.project.add_user(self.user, "VCS")

        self.assertTrue(self.user.has_perm("vcs.reset", self.component))
        self.assertFalse(self.user.has_perm("component.edit", self.component))
        self.assertTrue(os.path.exists(cast("str", self.de_translation.get_filename())))

        self.assertTrue(self.component.do_reset(self.get_request(), keep_changes=True))

        self.de_translation.refresh_from_db()
        self.assertTrue(os.path.exists(cast("str", self.de_translation.get_filename())))
        self.assertFalse(
            PendingUnitChange.objects.filter(
                unit__translation=self.de_translation
            ).exists()
        )
        self.assertEqual(
            self.get_unit(language="de", translation=self.de_translation).target,
            "Hallo Welt!\n",
        )

    def test_reset_keep_reports_missing_translation_file_without_creation_support(
        self,
    ) -> None:
        self.prepare_missing_translation_file(
            self.de_translation,
            target="Hallo Welt!\n",
            commit_to_remote=True,
        )
        self.restore_local_missing_translation_files(self.de_translation)
        self.component.new_base = "po/missing.pot"
        self.component.save(update_fields=["new_base"])

        request = self.get_request()
        self.assertFalse(self.component.do_reset(request, keep_changes=True))

        self.de_translation.refresh_from_db()
        self.assertFalse(
            os.path.exists(cast("str", self.de_translation.get_filename()))
        )
        self.assertTrue(
            PendingUnitChange.objects.filter(
                unit__translation=self.de_translation
            ).exists()
        )

        messages = [message.message for message in get_messages(request)]
        self.assertEqual(len(messages), 1)
        self.assertIn("configure the component", messages[0])
        self.assertIn(self.de_translation.filename, messages[0])

    def test_reset_keep_reports_invalid_restore_configuration_validation_error(
        self,
    ) -> None:
        self.prepare_missing_translation_file(
            self.de_translation,
            target="Hallo Welt!\n",
            commit_to_remote=True,
        )
        self.restore_local_missing_translation_files(self.de_translation)

        request = self.get_request()
        with patch.object(
            Component,
            "can_restore_missing_translation_file",
            autospec=True,
            side_effect=ValidationError("Invalid new translation base path."),
        ):
            self.assertFalse(self.component.do_reset(request, keep_changes=True))

        self.de_translation.refresh_from_db()
        self.assertFalse(
            os.path.exists(cast("str", self.de_translation.get_filename()))
        )
        self.assertTrue(
            PendingUnitChange.objects.filter(
                unit__translation=self.de_translation
            ).exists()
        )

        messages = [message.message for message in get_messages(request)]
        self.assertEqual(len(messages), 1)
        self.assertIn("Pending changes were kept", messages[0])
        self.assertIn(self.de_translation.filename, messages[0])

    def test_reset_keep_rolls_back_partial_missing_translation_restore(self) -> None:
        self.prepare_missing_translation_file(
            self.de_translation,
            target="Hallo Welt!\n",
            commit_to_remote=True,
        )
        self.component.push_on_commit = True
        self.component.save(update_fields=["push_on_commit"])
        it_translation = self.ensure_translation("it")
        self.prepare_missing_translation_file(
            it_translation,
            target="Ciao mondo!\n",
            commit_to_remote=True,
        )
        self.restore_local_missing_translation_files(
            self.de_translation, it_translation
        )

        restore_file = Component.restore_missing_translation_file
        restore_calls = 0

        def fail_second_restore(component, translation, **kwargs) -> None:
            nonlocal restore_calls

            restore_calls += 1
            if restore_calls == 2:
                msg = "restore failed"
                raise OSError(msg)
            restore_file(component, translation, **kwargs)

        request = self.get_request()
        with patch.object(
            Component,
            "restore_missing_translation_file",
            autospec=True,
            side_effect=fail_second_restore,
        ):
            self.assertFalse(self.component.do_reset(request, keep_changes=True))

        self.de_translation.refresh_from_db()
        it_translation.refresh_from_db()
        for translation in (self.de_translation, it_translation):
            self.assertFalse(os.path.exists(cast("str", translation.get_filename())))
            self.assertTrue(
                PendingUnitChange.objects.filter(unit__translation=translation).exists()
            )

        self.assertEqual(self.component.repository.count_outgoing(), 0)

        messages = [message.message for message in get_messages(request)]
        self.assertEqual(len(messages), 1)
        self.assertIn("Pending changes were kept", messages[0])

    def test_restore_pending_translation_files_checks_component_once(self) -> None:
        self.prepare_missing_translation_file(
            self.de_translation,
            target="Hallo Welt!\n",
        )
        it_translation = self.ensure_translation("it")
        self.prepare_missing_translation_file(
            it_translation,
            target="Ciao mondo!\n",
        )

        original_can_restore = Component.can_restore_missing_translation_file

        with (
            patch.object(
                Component, "drop_template_store_cache", autospec=True
            ) as mock_drop,
            patch.object(
                Component,
                "can_restore_missing_translation_file",
                autospec=True,
                side_effect=original_can_restore,
            ) as mock_can_restore,
            patch.object(
                Component, "restore_missing_translation_file", autospec=True
            ) as mock_restore,
            patch.object(Component, "send_post_commit_signal", autospec=True),
        ):
            self.assertTrue(
                self.component.restore_pending_translation_files(
                    request=self.get_request(),
                    user=self.user,
                )
            )

        self.assertEqual(mock_drop.call_count, 1)
        self.assertEqual(mock_can_restore.call_count, 1)
        self.assertEqual(mock_restore.call_count, 2)

    def test_restore_missing_translation_file_uses_repository_lock(self) -> None:
        self.prepare_missing_translation_file(self.de_translation)
        lock_states: list[bool] = []

        def record_add_language(*args, **kwargs) -> None:
            lock_states.append(self.component.repository.lock.is_locked)

        def record_git_commit(*args, **kwargs) -> bool:
            lock_states.append(self.component.repository.lock.is_locked)
            return True

        self.assertFalse(self.component.repository.lock.is_locked)
        with (
            patch.object(
                self.component.file_format_cls,
                "add_language",
                side_effect=record_add_language,
            ),
            patch.object(
                Translation,
                "git_commit",
                autospec=True,
                side_effect=record_git_commit,
            ),
            patch("weblate.trans.models.component.translation_post_add.send"),
        ):
            self.component.restore_missing_translation_file(
                self.de_translation, user=self.user
            )

        self.assertEqual(lock_states, [True, True])

    def test_restore_missing_translation_file_preserves_post_add_on_silent_commit(
        self,
    ) -> None:
        self.prepare_missing_translation_file(self.de_translation)
        with (
            patch.object(self.component.file_format_cls, "add_language"),
            patch.object(Translation, "git_commit", autospec=True) as mock_commit,
            patch(
                "weblate.trans.models.component.translation_post_add.send"
            ) as mock_send,
        ):
            self.component.restore_missing_translation_file(
                self.de_translation,
                user=self.user,
                signals=False,
            )

        mock_send.assert_called_once_with(
            sender=self.component.__class__, translation=self.de_translation
        )
        mock_commit.assert_called_once()
        self.assertFalse(mock_commit.call_args.kwargs["signals"])

    def test_restore_missing_translation_file_can_skip_post_add_signal(self) -> None:
        self.prepare_missing_translation_file(self.de_translation)
        with (
            patch.object(self.component.file_format_cls, "add_language"),
            patch.object(Translation, "git_commit", autospec=True) as mock_commit,
            patch(
                "weblate.trans.models.component.translation_post_add.send"
            ) as mock_send,
        ):
            self.component.restore_missing_translation_file(
                self.de_translation,
                user=self.user,
                send_post_add_signal=False,
            )

        mock_send.assert_not_called()
        mock_commit.assert_called_once()
        self.assertTrue(mock_commit.call_args.kwargs["signals"])

    def test_restore_pending_translation_files_handles_atomic_start_failure(
        self,
    ) -> None:
        self.prepare_missing_translation_file(
            self.de_translation,
            target="Hallo Welt!\n",
        )

        class FailingAtomic:
            def __enter__(self):
                msg = "atomic failed"
                raise OSError(msg)

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

        request = self.get_request()
        with (
            patch(
                "weblate.trans.models.component.transaction.atomic",
                return_value=FailingAtomic(),
            ),
            patch.object(self.component.repository, "reset") as mock_reset,
            patch.object(self.component.repository, "cleanup_files") as mock_cleanup,
            patch.object(
                Component, "restore_missing_translation_file", autospec=True
            ) as mock_restore,
        ):
            self.assertFalse(
                self.component.restore_pending_translation_files(
                    request=request,
                    user=self.user,
                )
            )

        self.de_translation.refresh_from_db()
        self.assertFalse(
            os.path.exists(cast("str", self.de_translation.get_filename()))
        )
        self.assertTrue(
            PendingUnitChange.objects.filter(
                unit__translation=self.de_translation
            ).exists()
        )
        mock_restore.assert_not_called()
        mock_reset.assert_called_once_with()
        mock_cleanup.assert_called_once_with()

        messages = [message.message for message in get_messages(request)]
        self.assertEqual(len(messages), 1)
        self.assertIn(self.de_translation.filename, messages[0])
        self.assertIn("Pending changes were kept", messages[0])

    def test_restore_pending_translation_files_cleans_failed_restore_artifacts(
        self,
    ) -> None:
        self.prepare_missing_translation_file(
            self.de_translation,
            target="Hallo Welt!\n",
        )
        addon_file = os.path.join(self.component.full_path, "po", "restore-extra.mo")

        def fail_commit(translation, *args, **kwargs) -> bool:
            pathlib.Path(addon_file).write_text("artifact", encoding="utf-8")
            translation.addon_commit_files.append(addon_file)
            msg = "commit failed"
            raise OSError(msg)

        request = self.get_request()
        with (
            self.component.repository.lock,
            patch.object(
                Translation,
                "git_commit",
                autospec=True,
                side_effect=fail_commit,
            ),
            patch("weblate.trans.models.component.translation_post_add.send"),
        ):
            self.assertFalse(
                self.component.restore_pending_translation_files(
                    request=request,
                    user=self.user,
                )
            )

        self.de_translation.refresh_from_db()
        self.assertTrue(os.path.exists(cast("str", self.de_translation.get_filename())))
        self.assertFalse(os.path.exists(addon_file))
        self.assertTrue(
            PendingUnitChange.objects.filter(
                unit__translation=self.de_translation
            ).exists()
        )

    def test_handle_restore_pending_translation_failure_without_translation(
        self,
    ) -> None:
        request = self.get_request()
        with (
            patch.object(self.component.repository, "reset") as mock_reset,
            patch.object(self.component.repository, "cleanup_files") as mock_cleanup,
            patch("weblate.trans.models.component.report_error") as mock_report_error,
        ):
            self.assertFalse(
                self.component.handle_restore_pending_translation_failure(
                    request=request,
                    missing_translations=[],
                    current_translation=None,
                    error=OSError("atomic failed"),
                )
            )

        mock_reset.assert_called_once_with()
        mock_cleanup.assert_called_once_with()
        mock_report_error.assert_called_once_with(
            "Could not recreate missing translation file during reset",
            project=self.component.project,
        )
        messages = [message.message for message in get_messages(request)]
        self.assertEqual(len(messages), 1)
        self.assertIn("Pending changes were kept", messages[0])


class ResetDiscardRevisionTest(ComponentTestCase):
    def test_reset_updates_stored_local_revision(self) -> None:
        start_rev = self.component.repository.last_revision

        self.change_unit("Ahoj svete!\n")
        self.component.commit_pending("test", self.user)

        self.component.refresh_from_db()
        stale_rev = self.component.local_revision
        self.assertNotEqual(start_rev, stale_rev)
        self.assertEqual(stale_rev, self.component.repository.last_revision)

        self.assertTrue(self.component.do_reset(self.get_request()))

        self.component.refresh_from_db()
        self.assertEqual(start_rev, self.component.repository.last_revision)
        self.assertEqual(start_rev, self.component.local_revision)


class TranslationRemoveRevisionTest(ComponentTestCase):
    def test_remove_updates_stored_local_revision(self) -> None:
        translation = self.component.translation_set.get(language_code="de")
        self.component.store_local_revision()
        self.component.refresh_from_db()
        start_rev = self.component.local_revision

        translation.remove(self.user)

        self.component.refresh_from_db()
        self.assertNotEqual(start_rev, self.component.local_revision)
        self.assertEqual(
            self.component.local_revision, self.component.repository.last_revision
        )


class LastCommitLookupTest(ComponentTestCase):
    def test_get_last_commit_keeps_stale_local_revision_unchanged(self) -> None:
        self.component.local_revision = "not-a-valid-revision"
        self.component.save(update_fields=["local_revision"])

        self.assertIsNone(self.component.get_last_commit())

        self.component.refresh_from_db()
        self.assertEqual("not-a-valid-revision", self.component.local_revision)


class UpdateBranchRevisionTest(ComponentTestCase):
    def test_update_branch_treats_stale_local_revision_as_update(self) -> None:
        current_head = self.component.repository.last_revision
        self.component.local_revision = ""
        self.component.processed_revision = current_head
        self.component.save(update_fields=["local_revision", "processed_revision"])

        with patch.object(
            Component, "trigger_post_update", autospec=True
        ) as mock_trigger:
            self.assertTrue(self.component.update_branch())

        self.component.refresh_from_db()
        self.assertEqual(current_head, self.component.local_revision)
        mock_trigger.assert_called_once()


class CleanupRevisionTest(ComponentTestCase):
    def test_cleanup_updates_stored_local_revision_when_head_changes(self) -> None:
        with (
            patch.object(
                Component,
                "try_get_local_head_revision",
                autospec=True,
                return_value="old",
            ),
            patch.object(
                Component,
                "get_local_head_revision",
                autospec=True,
                return_value="new",
            ),
            patch.object(
                Component, "store_local_revision", autospec=True
            ) as mock_store,
            patch.object(self.component.repository, "cleanup") as mock_cleanup,
        ):
            self.assertTrue(self.component.do_cleanup(self.get_request()))

        mock_cleanup.assert_called_once_with()
        mock_store.assert_called_once_with(self.component)

    def test_cleanup_reports_post_cleanup_head_read_failure(self) -> None:
        request = self.get_request()
        with (
            patch.object(
                Component,
                "try_get_local_head_revision",
                autospec=True,
                return_value="old",
            ),
            patch.object(
                Component,
                "get_local_head_revision",
                autospec=True,
                side_effect=RepositoryError(128, "broken HEAD"),
            ),
            patch.object(self.component.repository, "cleanup") as mock_cleanup,
            patch.object(
                Component, "store_local_revision", autospec=True
            ) as mock_store,
        ):
            self.assertFalse(self.component.do_cleanup(request))

        mock_cleanup.assert_called_once_with()
        mock_store.assert_not_called()
        messages = [message.message for message in get_messages(request)]
        self.assertEqual(len(messages), 1)
        self.assertIn("Could not clean the repository", messages[0])


class LinkedResetDiskStateTest(ComponentTestCase):
    def create_component(self):
        return self.create_link()

    def test_reset_keep_clears_disk_state_for_linked_components(self) -> None:
        unit = self.get_unit(translation=self.translation)
        unit.translate(self.user, "Ahoj svete!", STATE_TRANSLATED)
        unit.refresh_from_db()
        self.assertIn("disk_state", unit.details)

        with patch.object(Component, "queue_background_task", autospec=True):
            self.assertTrue(
                self.component.do_reset(self.get_request(), keep_changes=True)
            )

        unit.refresh_from_db()
        self.assertNotIn("disk_state", unit.details)
        self.assertTrue(
            PendingUnitChange.objects.for_component(
                cast("Component", self.component.linked_component),
                apply_filters=False,
                include_linked=True,
            )
            .filter(unit=unit)
            .exists()
        )

    def test_restore_pending_translation_files_signals_linked_component(self) -> None:
        root_component = cast("Component", self.component.linked_component)
        self.change_unit("Ahoj svete!\n", translation=self.translation)
        with root_component.repository.lock:
            pathlib.Path(cast("str", self.translation.get_filename())).unlink(
                missing_ok=True
            )

        with (
            patch.object(
                Component, "can_restore_missing_translation_file", return_value=True
            ),
            patch.object(Component, "restore_missing_translation_file", autospec=True),
            patch.object(
                Component, "send_post_commit_signal", autospec=True
            ) as mock_signal,
        ):
            self.assertTrue(
                root_component.restore_pending_translation_files(
                    request=self.get_request(),
                    user=self.user,
                )
            )

        mock_signal.assert_called_once_with(self.component, store_hash=False)


class ComponentHostKeyHandlingTest(SimpleTestCase):
    def test_handle_update_error_host_key_mismatch(self) -> None:
        component = SimpleNamespace(
            add_ssh_host_key=Mock(),
            get_ssh_host_key_error_message=Component.get_ssh_host_key_error_message,
            get_ssh_host_key_mismatch_error_message=(
                Component.get_ssh_host_key_mismatch_error_message
            ),
        )

        with self.assertRaises(ValidationError) as cm:
            Component.handle_update_error(
                component,
                HOST_KEY_MISMATCH_ERROR,
                retry=True,  # type: ignore[arg-type]
            )

        component.add_ssh_host_key.assert_not_called()
        self.assertEqual(
            cm.exception.message_dict["repo"],
            [
                "The SSH host key for the repository has changed. Verify the new fingerprint and replace the stored host key on the SSH page in the admin interface."
            ],
        )

    def test_repo_needs_push_host_key_mismatch_skips_tofu_retry(self) -> None:
        component = SimpleNamespace(
            repository=Mock(
                needs_push=Mock(
                    side_effect=RepositoryError(255, HOST_KEY_MISMATCH_ERROR)
                )
            ),
            error_text=Mock(return_value=HOST_KEY_MISMATCH_ERROR),
            add_alert=Mock(),
            add_ssh_host_key=Mock(),
            push_branch="main",
            project=Mock(),
        )

        with patch("weblate.trans.models.component.report_error") as mocked_report:
            self.assertFalse(
                Component.repo_needs_push(component)  # type: ignore[arg-type]
            )

        component.add_ssh_host_key.assert_not_called()
        component.add_alert.assert_called_once_with(
            "PushFailure", error=HOST_KEY_MISMATCH_ERROR
        )
        mocked_report.assert_called_once()


class LinkedEditTest(ViewTestCase):
    def create_component(self):
        return self.create_link()

    def test_linked(self) -> None:
        # Grab current revision
        start_rev = self.component.repository.last_revision

        # Translate all units
        for unit in Unit.objects.iterator():
            if not unit.is_source:
                unit.translate(self.user, "test", STATE_TRANSLATED)

        # No commit now
        self.assertEqual(start_rev, self.component.repository.last_revision)

        # Commit pending changes
        self.component.commit_pending("test", None)
        self.assertNotEqual(start_rev, self.component.repository.last_revision)
        self.assertEqual(4, self.component.repository.count_outgoing())


class ComponentEditTest(ViewTestCase):
    """Test for error handling."""

    @staticmethod
    def remove_units(store) -> None:
        store.store.units = []
        store.save()

    def test_unit_disappear(self) -> None:
        translation = self.component.translation_set.get(language_code="cs")

        if self.component.has_template():
            self.remove_units(self.component.template_store)
        self.remove_units(translation.store)

        # Clean class cache
        self.component.drop_template_store_cache()
        translation.drop_store_cache()

        unit = translation.unit_set.all()[0]

        self.assertTrue(unit.translate(self.user, ["Empty"], STATE_TRANSLATED))


class ComponentEditMonoTest(ComponentEditTest):
    """Test for error handling."""

    def create_component(self):
        return self.create_ts_mono()

    @staticmethod
    def remove_units(store) -> None:
        store.store.parse(store.store.XMLskeleton.replace("\n", "").encode())
        store.save()

    def test_unit_add(self) -> None:
        translation = self.component.translation_set.get(language_code="cs")

        self.remove_units(translation.store)

        # Clean class cache
        translation.drop_store_cache()

        unit = translation.unit_set.all()[0]

        self.assertTrue(unit.translate(self.user, ["Empty"], STATE_TRANSLATED))

    def test_readonly(self) -> None:
        source = self.component.translation_set.get(language_code="en")

        # The source string is always translated
        self.assertEqual(source.unit_set.all()[0].state, STATE_TRANSLATED)

        self.component.edit_template = False
        self.component.save()

        # It should be now read-only
        self.assertEqual(source.unit_set.all()[0].state, STATE_READONLY)


class ComponentKeyFilterTest(ViewTestCase):
    """Test the key filtering implementation in Component."""

    def create_component(self):
        return self.create_android(key_filter="^tr")

    def test_get_key_filter_re(self) -> None:
        self.assertEqual(self.component.key_filter_re.pattern, "^tr")

    def test_get_filtered_result(self) -> None:
        translation = self.component.translation_set.get(language_code="en")
        units = translation.unit_set.all()
        self.assertEqual(units.count(), 1)
        self.assertEqual(units.all()[0].context, "try")

    def test_change_key_filter(self) -> None:
        self.component.key_filter = "^th"
        self.component.save()
        self.assertEqual(self.component.key_filter_re.pattern, "^th")
        translations = self.component.translation_set.all()
        for translation in translations:
            units = translation.unit_set.all()
            self.assertEqual(units.count(), 1)
            self.assertEqual(units.all()[0].context, "thanks")

        self.component.key_filter = ""
        self.component.save()
        self.assertEqual(self.component.key_filter_re.pattern, "")
        translations = self.component.translation_set.all()
        for translation in translations:
            units = translation.unit_set.all()
            self.assertEqual(len(units), 4)

    def test_bilingual_component(self) -> None:
        project = self.component.project
        component = self.create_po(
            name="Bilingual Test", project=project, key_filter="^tr"
        )
        # Save should remove it
        self.assertEqual(component.key_filter, "")
        self.assertEqual(component.key_filter_re.pattern, "")

        # Verify validation will reject it
        component.key_filter = "^tr"
        with self.assertRaisesMessage(
            ValidationError,
            "To use the key filter, the file format must be monolingual.",
        ):
            component.clean()


class ComponentRepoWebTestCase(FixtureTestCase):
    def get_url(self) -> str | None:
        return self.component.get_repoweb_link("test.py", "42", user=self.user)

    def test_provided(self):
        self.component.repoweb = (
            "https://example.com/{{branch}}/f/{{filename}}#_{{line}}"
        )
        self.assertEqual("https://example.com/main/f/test.py#_42", self.get_url())

    def test_blank(self):
        self.assertIsNone(self.get_url())

    def test_repo_link_generation_bitbucket(self) -> None:
        """Test changing repo attribute to check repo generation links."""
        self.component.repo = "ssh://git@bitbucket.org/marcus/project-x.git"
        self.assertEqual(
            self.component.get_bitbucket_git_repoweb_template(),
            "https://bitbucket.org/marcus/project-x/blob/{{branch}}/{{filename}}#{{line}}",
        )

        self.component.repo = "git@bitbucket.org:marcus/project-x.git"
        self.assertEqual(
            self.component.get_bitbucket_git_repoweb_template(),
            "https://bitbucket.org/marcus/project-x/blob/{{branch}}/{{filename}}#{{line}}",
        )

        self.assertEqual(
            "https://bitbucket.org/marcus/project-x/blob/main/test.py#42",
            self.get_url(),
        )

    def test_repo_link_generation_github(self) -> None:
        """Test changing repo attribute to check repo generation links."""
        self.component.repo = "git://github.com/marcus/project-x.git"
        self.assertEqual(
            self.component.get_github_repoweb_template(),
            "https://github.com/marcus/project-x/blob/{{branch}}/{{filename}}#L{{line}}",
        )

        self.component.repo = "git@github.com:marcus/project-x.git"
        self.assertEqual(
            self.component.get_github_repoweb_template(),
            "https://github.com/marcus/project-x/blob/{{branch}}/{{filename}}#L{{line}}",
        )

        self.assertEqual(
            "https://github.com/marcus/project-x/blob/main/test.py#L42", self.get_url()
        )

    def test_repo_link_generation_pagure(self) -> None:
        """Test changing repo attribute to check repo generation links."""
        self.component.repo = "https://pagure.io/f/ATEST"
        self.assertEqual(
            self.component.get_pagure_repoweb_template(),
            "https://pagure.io/f/ATEST/blob/{{branch}}/f/{{filename}}/#_{{line}}",
        )

        self.assertEqual(
            "https://pagure.io/f/ATEST/blob/main/f/test.py/#_42", self.get_url()
        )

    def test_repo_link_generation_azure(self) -> None:
        """Test changing repo attribute to check repo generation links."""
        self.component.repo = "f@vs-ssh.visualstudio.com:v3/f/c/ATEST"
        self.assertEqual(
            self.component.get_azure_repoweb_template(),
            "https://dev.azure.com/f/c/_git/ATEST/blob/{{branch}}/{{filename}}#L{{line}}",
        )

        self.component.repo = "git@ssh.dev.azure.com:v3/f/c/ATEST"
        self.assertEqual(
            self.component.get_azure_repoweb_template(),
            "https://dev.azure.com/f/c/_git/ATEST/blob/{{branch}}/{{filename}}#L{{line}}",
        )

        self.component.repo = "https://f.visualstudio.com/c/_git/ATEST"
        self.assertEqual(
            self.component.get_azure_repoweb_template(),
            "https://dev.azure.com/f/c/_git/ATEST/blob/{{branch}}/{{filename}}#L{{line}}",
        )

        self.assertEqual(
            "https://dev.azure.com/f/c/_git/ATEST/blob/main/test.py#L42",
            self.get_url(),
        )
