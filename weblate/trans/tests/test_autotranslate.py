# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for automatic translation."""

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test.utils import override_settings
from django.urls import reverse

from weblate.trans.models import Component
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.db import TransactionsTestMixin


class AutoTranslationTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        # Need extra power
        self.user.is_superuser = True
        self.user.save()
        self.project.translation_review = True
        self.project.save()
        with override_settings(CREATE_GLOSSARIES=self.CREATE_GLOSSARIES):
            self.component2 = Component.objects.create(
                name="Test 2",
                slug="test-2",
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

    def test_none(self) -> None:
        """Test for automatic translation with no content."""
        response = self.client.post(
            reverse("auto_translation", kwargs=self.kw_translation)
        )
        self.assertRedirects(response, self.translation_url)

    def make_different(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")

    def perform_auto(self, expected=1, expected_count=None, **kwargs) -> None:
        self.make_different()
        path_params = {"path": [*self.component2.get_url_path(), "cs"]}
        url = reverse("auto_translation", kwargs=path_params)
        kwargs["auto_source"] = "others"
        kwargs["threshold"] = "100"
        if "filter_type" not in kwargs:
            kwargs["filter_type"] = "todo"
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
        translation = self.component2.translation_set.get(language_code="cs")
        translation.invalidate_cache()
        if expected_count is None:
            expected_count = expected
        if kwargs["mode"] == "suggest":
            self.assertEqual(translation.stats.suggestions, expected_count)
        else:
            self.assertEqual(translation.stats.translated, expected_count)

    def test_different(self) -> None:
        """Test for automatic translation with different content."""
        self.perform_auto()

    def test_suggest(self) -> None:
        """Test for automatic suggestion."""
        self.perform_auto(mode="suggest")
        self.perform_auto(0, 1, mode="suggest")

    def test_approved(self) -> None:
        """Test for automatic suggestion."""
        self.perform_auto(mode="approved")
        self.perform_auto(0, 1, mode="approved")

    def test_inconsistent(self) -> None:
        self.perform_auto(0, filter_type="check:inconsistent")

    def test_overwrite(self) -> None:
        self.perform_auto(overwrite="1")

    def test_labeling(self) -> None:
        self.perform_auto(overwrite="1")
        translation = self.component2.translation_set.get(language_code="cs")
        self.assertEqual(
            translation.unit_set.filter(
                labels__name="Automatically translated"
            ).count(),
            1,
        )
        self.edit_unit("Thank you for using Weblate.", "Díky za používání Weblate.")
        self.assertEqual(
            translation.unit_set.filter(
                labels__name="Automatically translated"
            ).count(),
            1,
        )
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", translation=translation)
        self.assertEqual(
            translation.unit_set.filter(
                labels__name="Automatically translated"
            ).count(),
            0,
        )

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
        call_command("auto_translate", "test", "test-2", "cs", source="test/test")

    def test_command_errors(self) -> None:
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "cs", user="invalid")
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "cs", source="invalid")
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "cs", source="test/invalid")
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "xxx")


class AutoTranslationMtTest(TransactionsTestMixin, ViewTestCase):
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
        if "filter_type" not in kwargs:
            kwargs["filter_type"] = "todo"
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

    def test_multi(self) -> None:
        """Test for automatic translation with more providers."""
        self.perform_auto(
            engines=["weblate", "weblate-translation-memory"], threshold=80
        )

    def test_inconsistent(self) -> None:
        self.perform_auto(
            0, filter_type="check:inconsistent", engines=["weblate"], threshold=80
        )

    def test_overwrite(self) -> None:
        self.perform_auto(overwrite="1", engines=["weblate"], threshold=80)
