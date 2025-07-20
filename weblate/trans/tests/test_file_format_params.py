# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


"""Test for File format params."""

from django.test.utils import override_settings
from django.urls import reverse

from weblate.lang.models import get_default_lang
from weblate.trans.models import Component
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.views import get_form_data


class BaseFileFormatsTest(ViewTestCase):
    def update_component_file_params(self, **file_param_kwargs):
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
        self.user.is_superuser = True
        self.user.save()
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
        component = self.get_new_component()
        self.assertFalse(component.file_format_params["po_line_wrap"])
        self.update_component_file_params(po_line_wrap=65535)
        self.assertEqual(component.file_format_params["po_line_wrap"], "65535")


class JsonParamsTest(BaseFileFormatsTest):
    def setUp(self):
        super().setUp()
        self.user.is_superuser = True
        self.user.save()

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
    def setUp(self):
        super().setUp()
        self.user.is_superuser = True
        self.user.save()

    def create_component(self) -> Component:
        return self.create_yaml()

    def test_customize(self) -> None:
        self.update_component_file_params(
            yaml_indent=8,
            yaml_line_wrap=100,
            yaml_line_break="dos",
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
