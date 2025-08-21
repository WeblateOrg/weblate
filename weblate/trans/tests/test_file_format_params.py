# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


"""Test for File format params."""

from django.test.utils import override_settings
from django.urls import reverse

from weblate.addons.gettext import MsgmergeAddon
from weblate.lang.models import get_default_lang
from weblate.trans.file_format_params import get_default_params_for_file_format
from weblate.trans.models import Component
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.views import get_form_data


class BaseFileFormatsTest(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.user.is_superuser = True
        self.user.save()

    def update_component_file_params(self, **file_param_kwargs):
        file_param_kwargs = (
            get_default_params_for_file_format(self.component.file_format)
            | file_param_kwargs
        )
        url = reverse("settings", kwargs={"path": self.component.get_url_path()})
        response = self.client.get(url)
        data = get_form_data(response.context["form"].initial)
        data.update(
            {f"file_format_params_{k}": v for k, v in file_param_kwargs.items()}
        )
        self.client.post(url, data, follow=True)
        self.component.refresh_from_db()


class ComponentFileFormatsParamsTest(BaseFileFormatsTest):
    def client_create_component(self, result, **kwargs):
        params = {
            "name": "New Component With File Params",
            "slug": "new-component-with-file-params",
            "project": self.project.pk,
            "vcs": "git",
            "repo": self.component.get_repo_link_url(),
            "file_format": "po",
            "filemask": "po/*.po",
            "new_base": "po/project.pot",
            "new_lang": "add",
            "language_regex": "^[^.]+$",
            "source_language": get_default_lang(),
        }
        params.update(kwargs)
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            response = self.client.post(reverse("create-component-vcs"), params)
        if result:
            self.assertEqual(response.status_code, 302)
        else:
            self.assertEqual(response.status_code, 200)
        return response

    def get_new_component(
        self, slug: str = "new-component-with-file-params"
    ) -> Component:
        return Component.objects.get(slug=slug, project_id=self.project.pk)

    def test_file_params(self):
        self.client_create_component(
            True,
            file_format_params_po_line_wrap="77",
            json_sort_keys=True,
        )
        component = self.get_new_component()
        # check that only the expected parameters are set
        self.assertEqual(component.file_format_params["po_line_wrap"], "77")
        self.assertNotIn("json_sort_keys", component.file_format_params)

    def test_file_params_invalid(self):
        self.client_create_component(False, file_format_params_po_line_wrap="999999")
        with self.assertRaises(Component.DoesNotExist):
            self.get_new_component()

    def test_file_params_update(self):
        self.client_create_component(True)
        self.component = self.get_new_component()
        self.assertFalse(self.component.file_format_params["po_line_wrap"])
        self.update_component_file_params(po_line_wrap=65535)
        self.assertEqual(self.component.file_format_params["po_line_wrap"], "65535")

    def test_create_component_from_existing(self):
        self.update_component_file_params(
            po_line_wrap=-1, po_keep_previous=False, po_fuzzy_matching=False
        )

        response = self.client.post(
            reverse("create-component"),
            {
                "origin": "existing",
                "name": "Create Component From Existing",
                "slug": "create-component-from-existing",
                "component": self.component.pk,
                "is_glossary": self.component.is_glossary,
            },
            follow=True,
        )

        create_url = (
            reverse("create-component-vcs")
            + f"?source_component={self.component.pk}#existing"
        )
        data = response.context["form"].initial
        data.pop("category", None)
        data["project"] = self.component.project_id
        data["source_language"] = self.component.source_language_id
        data["discovery"] = next(
            i
            for i, k in response.context["form"].fields["discovery"].choices
            if self.component.filemask in k
        )
        response = self.client.post(
            create_url,
            data,
            follow=True,
        )

        data = response.context["form"].initial
        data.pop("category", None)
        data["project"] = self.component.project_id
        data["source_language"] = self.component.source_language_id
        data["language_regex"] = "^[^.]+$"
        data["new_lang"] = "add"
        data.update(
            {
                f"file_format_params_{k}": v
                for k, v in data["file_format_params"].items()
            }
        )
        self.client.post(create_url, data, follow=True)

        new_component = Component.objects.get(slug="create-component-from-existing")
        self.assertEqual(new_component.file_format_params["po_line_wrap"], "-1")
        self.assertEqual(new_component.file_format_params["po_keep_previous"], False)
        self.assertEqual(new_component.file_format_params["po_fuzzy_matching"], False)


class JsonParamsTest(BaseFileFormatsTest):
    def create_component(self) -> Component:
        return self.create_json_mono(suffix="mono-sync")

    def assert_customize(self, expected: str, *, is_compact: bool = False) -> str:
        rev = self.component.repository.last_revision
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.get_translation().commit_pending("test", None)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn(f'{expected}"try"', commit)
        if is_compact:
            self.assertIn('":"', commit)
        else:
            self.assertIn(': "', commit)
        return commit

    def test_customize(self) -> None:
        self.update_component_file_params(
            json_indent=8,
            json_indent_style="spaces",
            json_sort_keys=True,
        )

        commit = self.assert_customize("        ")
        self.assertIn(
            '''"orangutan": "",
+        "thanks": "",
+        "try": ""''',
            commit,
        )

    def test_customize_no_indent(self) -> None:
        self.update_component_file_params(
            json_indent=0,
            json_indent_style="spaces",
            json_sort_keys=True,
        )

        commit = self.assert_customize("+")
        self.assertIn(
            '''"orangutan": "",
+"thanks": "",
+"try": ""''',
            commit,
        )

    def test_customize_no_sort(self) -> None:
        self.update_component_file_params(
            json_indent=8,
            json_indent_style="spaces",
            json_sort_keys=False,
        )
        commit = self.assert_customize("        ")
        self.assertIn(
            '''"orangutan": "",
+        "try": "",
+        "thanks": ""''',
            commit,
        )

    def test_customize_tabs(self) -> None:
        self.update_component_file_params(
            json_indent=8,
            json_indent_style="tabs",
            json_sort_keys=True,
        )
        self.assert_customize("\t\t\t\t\t\t\t\t")

    def test_customize_compact_mode_on(self) -> None:
        self.update_component_file_params(
            json_indent=4,
            json_indent_style="spaces",
            json_sort_keys=True,
            json_use_compact_separators=True,
        )
        self.assert_customize("    ", is_compact=True)

    def test_customize_compact_mode_off(self) -> None:
        self.update_component_file_params(
            json_indent=4,
            json_indent_style="spaces",
            json_sort_keys=True,
            json_use_compact_separators=False,
        )
        self.assert_customize("    ", is_compact=False)


class YAMLParamsTest(BaseFileFormatsTest):
    def create_component(self) -> Component:
        return self.create_yaml()

    def assert_customize(self, expected: str) -> None:
        rev = self.component.repository.last_revision
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.get_translation().commit_pending("test", None)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn(f"{expected}try:", commit)
        self.assertIn("cs.yml", commit)
        with open(self.get_translation().get_filename(), "rb") as handle:
            self.assertIn(b"\r\n", handle.read())

    def test_customize(self) -> None:
        self.update_component_file_params(
            yaml_indent=8,
            yaml_line_wrap=100,
            yaml_line_break="dos",
        )
        self.assert_customize("        ")


class XMLParamsTest(BaseFileFormatsTest):
    def create_component(self) -> Component:
        return self.create_xliff("complex")

    def test_closing_tags(self, closing_tags_active: bool = True) -> None:
        self.update_component_file_params(xml_closing_tags=closing_tags_active)
        rev = self.component.repository.last_revision
        self.edit_unit("Thank you for using Weblate", "Děkujeme, že používáte Weblate")
        self.get_translation().commit_pending("test", None)
        self.assertNotEqual(rev, self.component.repository.last_revision)

        commit = self.component.repository.show(self.component.repository.last_revision)
        if closing_tags_active:
            self.assertIn("<target></target>", commit)
            self.assertNotIn("<target/>", commit)
        else:
            self.assertIn("<target/>", commit)

    def test_closing_tags_off(self) -> None:
        self.test_closing_tags(closing_tags_active=False)


class GettextParamsTest(BaseFileFormatsTest):
    def create_component(self):
        return self.create_po_new_base(new_lang="add")

    def test_msgmerge(self, wrapped=True) -> None:
        self.assertTrue(MsgmergeAddon.can_install(self.component, None))
        rev = self.component.repository.last_revision
        addon = MsgmergeAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, "", False)
        self.assertEqual(rev, self.component.repository.last_revision)
        addon.post_update(self.component, rev, False)
        self.assertEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("po/cs.po", commit)
        self.assertEqual('msgid "Try using Weblate demo' in commit, not wrapped)

    def test_msgmerge_nowrap(self) -> None:
        self.update_component_file_params(po_line_wrap=-1)
        self.test_msgmerge(False)

    def test_store(self) -> None:
        self.update_component_file_params(
            po_line_wrap=-1, po_fuzzy_matching=False, po_keep_previous=False
        )
        rev = self.component.repository.last_revision
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.get_translation().commit_pending("test", None)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn(
            "Last-Translator: Weblate Test <weblate@example.org>\\nLanguage", commit
        )

    def test_msgmerge_no_location(self) -> None:
        self.update_component_file_params(po_no_location=True)
        rev = self.component.repository.last_revision
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertIn("#: main.c:", commit)
        addon = MsgmergeAddon.create(component=self.component)
        self.assertNotEqual(rev, self.component.repository.last_revision)
        rev = self.component.repository.last_revision
        addon.post_update(self.component, rev, False)
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.get_translation().commit_pending("test", None)
        commit = self.component.repository.show(self.component.repository.last_revision)
        self.assertNotIn("#: main.c:", commit)

    def test_msgmerge_args(self) -> None:
        from weblate.formats.base import BilingualUpdateMixin

        # default parameters
        self.assertEqual(
            BilingualUpdateMixin.get_msgmerge_args(self.component), ["--previous"]
        )

        self.update_component_file_params(
            po_fuzzy_matching=False,
            po_keep_previous=False,
            po_no_location=True,
            po_line_wrap=77,
        )

        # if Msgmerge addon is not installed, only default parameters are returned
        self.assertEqual(
            BilingualUpdateMixin.get_msgmerge_args(self.component), ["--previous"]
        )

        MsgmergeAddon.create(component=self.component)

        msgmerge_args = BilingualUpdateMixin.get_msgmerge_args(self.component)
        self.assertNotIn("--previous", msgmerge_args)
        self.assertIn("--no-fuzzy-matching", msgmerge_args)
        self.assertIn("--no-location", msgmerge_args)

        self.update_component_file_params(
            po_fuzzy_matching=False,
            po_keep_previous=False,
            po_no_location=True,
            po_line_wrap=-1,
        )
        self.assertIn(
            "--no-wrap", BilingualUpdateMixin.get_msgmerge_args(self.component)
        )
