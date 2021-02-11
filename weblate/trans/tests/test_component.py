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
"""Test for translation models."""
import os

from django.core.exceptions import ValidationError
from django.test.utils import override_settings

from weblate.checks.models import Check
from weblate.lang.models import Language
from weblate.trans.exceptions import FileParseError
from weblate.trans.models import Change, Component, Project, Unit
from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.files import remove_tree
from weblate.utils.state import STATE_EMPTY, STATE_READONLY, STATE_TRANSLATED


class ComponentTest(RepoTestCase):
    """Component object testing."""

    def verify_component(
        self,
        component,
        translations,
        lang=None,
        units=0,
        unit="Hello, world!\n",
        source_units=None,
    ):
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
                    "Unit not found, all units: {}".format(
                        "\n".join(translation.unit_set.values_list("source", flat=True))
                    ),
                )

        if component.has_template() and component.edit_template:
            translation = component.translation_set.get(filename=component.template)
            # Count units in it
            self.assertEqual(translation.unit_set.count(), units)
            # Count translated units in it
            self.assertEqual(
                translation.unit_set.filter(state__gte=STATE_TRANSLATED).count(),
                source_units,
            )

    def test_create(self):
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

    def test_create_dot(self):
        component = self._create_component("po", "./po/*.po")
        self.verify_component(component, 4, "cs", 4)
        self.assertTrue(os.path.exists(component.full_path))
        self.assertEqual("po/*.po", component.filemask)

    def test_create_iphone(self):
        component = self.create_iphone()
        self.verify_component(component, 2, "cs", 4)

    def test_create_ts(self):
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

    def test_create_ts_mono(self):
        component = self.create_ts_mono()
        self.verify_component(component, 2, "cs", 4)

    def test_create_appstore(self):
        component = self.create_appstore()
        self.verify_component(
            component, 2, "cs", 3, "Weblate - continuous localization"
        )

    def test_create_po_pot(self):
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

    def test_create_filtered(self):
        component = self._create_component("po", "po/*.po", language_regex="^cs$")
        self.verify_component(component, 2, "cs", 4)

    def test_create_po(self):
        component = self.create_po()
        self.verify_component(component, 4, "cs", 4)

    def test_create_srt(self):
        component = self.create_srt()
        self.verify_component(component, 2, "cs", 4, "Hello, world!")

    def test_create_po_mercurial(self):
        component = self.create_po_mercurial()
        self.verify_component(component, 4, "cs", 4)

    def test_create_po_branch(self):
        component = self.create_po_branch()
        self.verify_component(component, 4, "cs", 4)

    def test_create_po_mercurial_branch(self):
        component = self.create_po_mercurial_branch()
        self.verify_component(component, 4, "cs", 4)

    def test_create_po_push(self):
        component = self.create_po_push()
        self.verify_component(component, 4, "cs", 4)

    def test_create_po_svn(self):
        component = self.create_po_svn()
        self.verify_component(component, 4, "cs", 4)

    def test_create_po_empty(self):
        component = self.create_po_empty()
        self.verify_component(component, 1, "en", 4)
        unit = Unit.objects.get(source="Hello, world!\n")
        self.assertEqual(unit.state, STATE_READONLY)
        self.assertEqual(unit.target, "Hello, world!\n")

    def test_create_po_link(self):
        component = self.create_po_link()
        self.verify_component(component, 5, "cs", 4)

    def test_create_po_mono(self):
        component = self.create_po_mono()
        self.verify_component(component, 4, "cs", 4)

    def test_create_android(self):
        component = self.create_android()
        self.verify_component(component, 2, "cs", 4)

    def test_create_android_broken(self):
        component = self.create_android(suffix="-broken")
        self.verify_component(component, 1, "en", 3)

    def test_create_json(self):
        component = self.create_json()
        self.verify_component(component, 2, "cs", 4)

    def test_create_json_mono(self):
        component = self.create_json_mono()
        self.verify_component(component, 2, "cs", 4)

    def test_create_json_nested(self):
        component = self.create_json_mono(suffix="nested")
        self.verify_component(component, 2, "cs", 4)

    def test_create_json_webextension(self):
        component = self.create_json_webextension()
        self.verify_component(component, 2, "cs", 4)

    def test_create_json_intermediate(self):
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

    def test_switch_json_intermediate(self):
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

    def test_create_json_intermediate_empty(self):
        # This should automatically create empty English file
        component = self.create_json_intermediate_empty()
        # The English one should have source from intermediate and no translated units
        self.verify_component(component, 1, "en", 4, "Hello world!\n", source_units=0)

    def test_create_joomla(self):
        component = self.create_joomla()
        self.verify_component(component, 3, "cs", 4)

    def test_create_ini(self):
        component = self.create_ini()
        self.verify_component(component, 2, "cs", 4, "Hello, world!\\n")

    def test_create_tsv_simple(self):
        component = self._create_component("csv-simple", "tsv/*.txt")
        self.verify_component(component, 2, "cs", 4, "Hello, world!")

    def test_create_tsv_simple_iso(self):
        component = self._create_component("csv-simple-iso", "tsv/*.txt")
        self.verify_component(component, 2, "cs", 4, "Hello, world!")

    def test_create_csv(self):
        component = self.create_csv()
        self.verify_component(component, 2, "cs", 4)

    def test_create_csv_mono(self):
        component = self.create_csv_mono()
        self.verify_component(component, 2, "cs", 4)

    def test_create_php_mono(self):
        component = self.create_php_mono()
        self.verify_component(component, 2, "cs", 4)

    def test_create_tsv(self):
        component = self.create_tsv()
        self.verify_component(component, 2, "cs", 4, "Hello, world!")

    def test_create_java(self):
        component = self.create_java()
        self.verify_component(component, 3, "cs", 4)

    def test_create_xliff(self):
        component = self.create_xliff()
        self.verify_component(component, 2, "cs", 4)

    def test_create_xliff_complex(self):
        component = self.create_xliff("complex")
        self.verify_component(component, 2, "cs", 4)

    def test_create_xliff_mono(self):
        component = self.create_xliff_mono()
        self.verify_component(component, 2, "cs", 4)

    def test_create_xliff_dph(self):
        component = self.create_xliff(
            "DPH", source_language=Language.objects.get(code="cs")
        )
        self.verify_component(component, 2, "en", 9, "DPH")

    def test_create_xliff_empty(self):
        component = self.create_xliff(
            "EMPTY", source_language=Language.objects.get(code="cs")
        )
        self.verify_component(component, 2, "en", 6, "DPH")

    def test_create_xliff_resname(self):
        component = self.create_xliff(
            "Resname", source_language=Language.objects.get(code="cs")
        )
        self.verify_component(component, 2, "en", 2, "Hi")

    def test_create_xliff_only_resname(self):
        component = self.create_xliff("only-resname")
        self.verify_component(component, 2, "cs", 4)

    def test_create_resx(self):
        component = self.create_resx()
        self.verify_component(component, 2, "cs", 4)

    def test_create_yaml(self):
        component = self.create_yaml()
        self.verify_component(component, 2, "cs", 4)

    def test_create_ruby_yaml(self):
        component = self.create_ruby_yaml()
        self.verify_component(component, 2, "cs", 4)

    def test_create_dtd(self):
        component = self.create_dtd()
        self.verify_component(component, 2, "cs", 4)

    def test_create_html(self):
        component = self.create_html()
        self.verify_component(component, 2, "cs", 4, unit="Hello, world!")

    def test_create_idml(self):
        component = self.create_idml()
        self.verify_component(
            component,
            1,
            "en",
            5,
            unit="""<g id="0"><g id="1">THE HEADLINE HERE</g></g>""",
        )

    def test_create_odt(self):
        component = self.create_odt()
        self.verify_component(component, 2, "cs", 4, unit="Hello, world!")

    def test_create_winrc(self):
        component = self.create_winrc()
        self.verify_component(component, 2, "cs-CZ", 4)

    def test_create_tbx(self):
        component = self.create_tbx()
        self.verify_component(component, 2, "cs", 4, unit="address bar")

    def test_link(self):
        component = self.create_link()
        self.verify_component(component, 4, "cs", 4)

    def test_flags(self):
        """Translation flags validation."""
        component = self.create_component()
        component.full_clean()

        component.check_flags = "ignore-inconsistent"
        component.full_clean()

        component.check_flags = "rst-text,ignore-inconsistent"
        component.full_clean()

        component.check_flags = "nonsense"
        self.assertRaisesMessage(
            ValidationError,
            'Invalid translation flag: "nonsense"',
            component.full_clean,
        )

        component.check_flags = "rst-text,ignore-nonsense"
        self.assertRaisesMessage(
            ValidationError,
            'Invalid translation flag: "ignore-nonsense"',
            component.full_clean,
        )

    def test_lang_code_template(self):
        component = Component(project=Project())
        component.filemask = "Solution/Project/Resources.*.resx"
        component.template = "Solution/Project/Resources.resx"
        self.assertEqual(
            component.get_lang_code("Solution/Project/Resources.resx"), "en"
        )

    def test_switch_branch(self):
        component = self.create_po()
        # Switch to translation branch
        self.verify_component(component, 4, "cs", 4)
        component.branch = "translations"
        component.filemask = "translations/*.po"
        component.clean()
        component.save()
        self.verify_component(component, 4, "cs", 4)
        # Switch back to master branch
        component.branch = "master"
        component.filemask = "po/*.po"
        component.clean()
        component.save()
        self.verify_component(component, 4, "cs", 4)

    def test_switch_branch_mercurial(self):
        component = self.create_po_mercurial()
        # Switch to translation branch
        self.verify_component(component, 4, "cs", 4)
        component.branch = "translations"
        component.filemask = "translations/*.po"
        component.clean()
        component.save()
        self.verify_component(component, 4, "cs", 4)
        # Switch back to master branch
        component.branch = "default"
        component.filemask = "po/*.po"
        component.clean()
        component.save()
        self.verify_component(component, 4, "cs", 4)

    def test_update_checks(self):
        """Setting of check_flags changes checks for related units."""
        component = self.create_component()
        self.assertEqual(Check.objects.count(), 3)
        check = Check.objects.all()[0]
        component.check_flags = f"ignore-{check.check}"
        component.save()
        self.assertEqual(Check.objects.count(), 0)

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
                "filter_type": "todo",
                "auto_source": "mt",
                "component": "",
                "engines": ["weblate-translation-memory"],
                "threshold": "80",
            },
        }
    )
    def test_create_autoaddon(self):
        component = self.create_idml()
        self.assertEqual(
            set(component.addon_set.values_list("name", flat=True)),
            {"weblate.flags.same_edit", "weblate.autotranslate.autotranslate"},
        )


class ComponentDeleteTest(RepoTestCase):
    """Component object deleting testing."""

    def test_delete(self):
        component = self.create_component()
        self.assertTrue(os.path.exists(component.full_path))
        component.delete()
        self.assertFalse(os.path.exists(component.full_path))
        self.assertEqual(1, Component.objects.count())

    def test_delete_link(self):
        component = self.create_link()
        main_project = Component.objects.get(slug="test")
        self.assertTrue(os.path.exists(main_project.full_path))
        component.delete()
        self.assertTrue(os.path.exists(main_project.full_path))

    def test_delete_all(self):
        component = self.create_component()
        self.assertTrue(os.path.exists(component.full_path))
        Component.objects.all().delete()
        self.assertFalse(os.path.exists(component.full_path))

    def test_delete_with_checks(self):
        """Test deleting of component with checks works."""
        component = self.create_component()
        # Introduce missing source string check. This can happen when adding new check
        # on upgrade or similar situation.
        unit = Unit.objects.filter(check__isnull=False).first().source_unit
        unit.source = "Test..."
        unit.save(update_fields=["source"])
        unit.check_set.filter(check="ellipisis").delete()
        component.delete()


class ComponentChangeTest(RepoTestCase):
    """Component object change testing."""

    def test_rename(self):
        link_component = self.create_link()
        component = link_component.linked_component
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

    def test_unlink_clean(self):
        """Test changing linked component to real repo based one."""
        component = self.create_link()
        component.repo = component.linked_component.repo
        component.clean()
        component.save()

    def test_unlink(self):
        """Test changing linked component to real repo based one."""
        component = self.create_link()
        component.repo = component.linked_component.repo
        component.save()

    def test_change_project(self):
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

    def test_change_to_mono(self):
        """Test swtiching to monolingual format on the fly."""
        component = self._create_component("po", "po-mono/*.po")
        self.assertEqual(component.translation_set.count(), 4)
        component.file_format = "po-mono"
        component.template = "po-mono/en.po"
        component.save()
        self.assertEqual(component.translation_set.count(), 4)

    def test_autolock(self):
        component = self.create_component()
        start = component.change_set.count()

        component.add_alert("MergeFailure")
        self.assertTrue(component.locked)
        # Locked event, alert added
        self.assertEqual(component.change_set.count() - start, 2)

        change = component.change_set.get(action=Change.ACTION_LOCK)
        self.assertEqual(change.details, {"auto": True})
        self.assertEqual(change.get_action_display(), "Component automatically locked")

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


class ComponentValidationTest(RepoTestCase):
    """Component object validation testing."""

    def setUp(self):
        super().setUp()
        self.component = self.create_component()
        # Ensure we have correct component
        self.component.full_clean()

    def test_commit_message(self):
        """Invalid commit message."""
        self.component.commit_message = "{% if %}"
        with self.assertRaises(ValidationError):
            self.component.full_clean()

    def test_filemask(self):
        """Invalid mask."""
        self.component.filemask = "foo/x.po"
        self.assertRaisesMessage(
            ValidationError,
            "Filemask does not contain * as a language placeholder!",
            self.component.full_clean,
        )

    def test_no_matches(self):
        """Not matching mask."""
        self.component.filemask = "foo/*.po"
        self.assertRaisesMessage(
            ValidationError,
            "The filemask did not match any files.",
            self.component.full_clean,
        )

    def test_fileformat(self):
        """Unknown file format."""
        self.component.file_format = "i18next"
        self.component.filemask = "invalid/*.invalid"
        self.assertRaisesMessage(
            ValidationError,
            "Could not parse 2 matched files.",
            self.component.full_clean,
        )

    def test_repoweb(self):
        """Invalid repoweb format."""
        self.component.repoweb = "http://{{foo}}/{{bar}}/%72"
        self.assertRaisesMessage(
            ValidationError, 'Undefined variable: "foo"', self.component.full_clean
        )
        self.component.repoweb = ""

    def test_link_incomplete(self):
        """Incomplete link."""
        self.component.repo = "weblate://foo"
        self.component.push = ""
        self.assertRaisesMessage(
            ValidationError,
            "Invalid link to a Weblate project, " "use weblate://project/component.",
            self.component.full_clean,
        )

    def test_link_nonexisting(self):
        """Link to non existing project."""
        self.component.repo = "weblate://foo/bar"
        self.component.push = ""
        self.assertRaisesMessage(
            ValidationError,
            "Invalid link to a Weblate project, " "use weblate://project/component.",
            self.component.full_clean,
        )

    def test_link_self(self):
        """Link pointing to self."""
        self.component.repo = "weblate://test/test"
        self.component.push = ""
        self.assertRaisesMessage(
            ValidationError,
            "Invalid link to a Weblate project, cannot link it to itself!",
            self.component.full_clean,
        )

    def test_validation_mono(self):
        self.component.project.delete()
        project = self.create_po_mono()
        # Correct project
        project.full_clean()
        # Not existing file
        project.template = "not-existing"
        with self.assertRaisesMessage(ValidationError, "File does not exist."):
            project.full_clean()

    def test_validation_language_re(self):
        self.component.language_regex = "[-"
        with self.assertRaises(ValidationError):
            self.component.full_clean()

    def test_validation_newlang(self):
        self.component.new_base = "po/project.pot"
        self.component.save()

        self.component.full_clean()

        self.component.new_lang = "add"
        self.component.save()

        # Check that it doesn't warn about not supported format
        self.component.full_clean()

        self.component.file_format = "po"
        self.component.save()

        # Clean class cache, pylint: disable=protected-access
        del self.component.__dict__["file_format"]

        # With correct format it should validate
        self.component.full_clean()

    def test_lang_code(self):
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
        self.assertEqual(project.get_language_alias("xx"), "cs")
        self.assertRaisesMessage(
            ValidationError,
            "The language code for "
            "Solution/Project/Resources.resx"
            " was empty, please check the filemask.",
            component.clean_lang_codes,
            [
                "Solution/Project/Resources.resx",
                "Solution/Project/Resources.de.resx",
                "Solution/Project/Resources.es.resx",
                "Solution/Project/Resources.es-mx.resx",
                "Solution/Project/Resources.fr.resx",
                "Solution/Project/Resources.fr-fr.resx",
            ],
        )

    def test_lang_code_double(self):
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

    def test_lang_code_plus(self):
        component = Component(project=Project())
        component.filemask = "po/*/master/pages/C_and_C++.po"
        self.assertEqual(
            component.get_lang_code("po/cs/master/pages/C_and_C++.po"),
            "cs",
        )


class ComponentErrorTest(RepoTestCase):
    """Test for error handling."""

    def setUp(self):
        super().setUp()
        self.component = self.create_ts_mono()
        # Change to invalid push URL
        self.component.repo = "file:/dev/null"
        self.component.push = "file:/dev/null"
        self.component.save()

    def test_failed_update(self):
        self.assertFalse(self.component.do_update())

    def test_failed_update_remote(self):
        self.assertFalse(self.component.update_remote_branch())

    def test_failed_push(self):
        testfile = os.path.join(self.component.full_path, "README.md")
        with open(testfile, "a") as handle:
            handle.write("CHANGE")
        with self.component.repository.lock:
            self.component.repository.commit("test", files=["README.md"])
        self.assertFalse(self.component.do_push(None))

    def test_failed_reset(self):
        # Corrupt Git database so that reset fails
        remove_tree(os.path.join(self.component.full_path, ".git", "objects", "pack"))
        self.assertFalse(self.component.do_reset(None))

    def test_invalid_templatename(self):
        self.component.template = "foo.bar"
        self.component.drop_template_store_cache()

        with self.assertRaises(FileParseError):
            self.component.template_store

        with self.assertRaises(ValidationError):
            self.component.clean()

    def test_invalid_filename(self):
        translation = self.component.translation_set.get(language_code="cs")
        translation.filename = "foo.bar"
        with self.assertRaises(FileParseError):
            translation.store
        with self.assertRaises(ValidationError):
            translation.clean()

    def test_invalid_storage(self):
        testfile = os.path.join(self.component.full_path, "ts-mono", "cs.ts")
        with open(testfile, "a") as handle:
            handle.write("CHANGE")
        translation = self.component.translation_set.get(language_code="cs")
        with self.assertRaises(FileParseError):
            translation.store
        with self.assertRaises(ValidationError):
            translation.clean()

    def test_invalid_template_storage(self):
        testfile = os.path.join(self.component.full_path, "ts-mono", "en.ts")
        with open(testfile, "a") as handle:
            handle.write("CHANGE")
        self.component.drop_template_store_cache()

        with self.assertRaises(FileParseError):
            self.component.template_store
        with self.assertRaises(ValidationError):
            self.component.clean()

    def test_change_source_language(self):
        self.component.source_language = Language.objects.get(code="cs")
        with self.assertRaises(ValidationError):
            self.component.clean()


class LinkedEditTest(ViewTestCase):
    def create_component(self):
        return self.create_link()

    def test_linked(self):
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
    def remove_units(store):
        store.store.units = []
        store.save()

    def test_unit_disappear(self):
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
    def remove_units(store):
        store.store.parse(store.store.XMLskeleton.replace("\n", "").encode())
        store.save()

    def test_unit_add(self):
        translation = self.component.translation_set.get(language_code="cs")

        self.remove_units(translation.store)

        # Clean class cache
        translation.drop_store_cache()

        unit = translation.unit_set.all()[0]

        self.assertTrue(unit.translate(self.user, ["Empty"], STATE_TRANSLATED))

    def test_readonly(self):
        source = self.component.translation_set.get(language_code="en")

        # The source string is always translated
        self.assertEqual(source.unit_set.all()[0].state, STATE_TRANSLATED)

        self.component.edit_template = False
        self.component.save()

        # It should be now read only
        self.assertEqual(source.unit_set.all()[0].state, STATE_READONLY)
