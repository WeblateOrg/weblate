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

"""Test for automatic translation."""

from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse

from weblate.trans.models import Component
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.db import using_postgresql


class AutoTranslationTest(ViewTestCase):
    def setUp(self):
        super().setUp()
        # Need extra power
        self.user.is_superuser = True
        self.user.save()
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

    def test_none(self):
        """Test for automatic translation with no content."""
        response = self.client.post(
            reverse("auto_translation", kwargs=self.kw_translation)
        )
        self.assertRedirects(response, self.translation_url)

    def make_different(self):
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")

    def perform_auto(self, expected=1, expected_count=None, **kwargs):
        self.make_different()
        params = {"project": "test", "lang": "cs", "component": "test-2"}
        url = reverse("auto_translation", kwargs=params)
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

        self.assertRedirects(response, reverse("translation", kwargs=params))
        # Check we've translated something
        translation = self.component2.translation_set.get(language_code="cs")
        translation.invalidate_cache()
        if expected_count is None:
            expected_count = expected
        if kwargs["mode"] == "suggest":
            self.assertEqual(translation.stats.suggestions, expected_count)
        else:
            self.assertEqual(translation.stats.translated, expected_count)

    def test_different(self):
        """Test for automatic translation with different content."""
        self.perform_auto()

    def test_suggest(self):
        """Test for automatic suggestion."""
        self.perform_auto(mode="suggest")
        self.perform_auto(0, 1, mode="suggest")

    def test_inconsistent(self):
        self.perform_auto(0, filter_type="check:inconsistent")

    def test_overwrite(self):
        self.perform_auto(overwrite="1")

    def test_command(self):
        call_command("auto_translate", "test", "test", "cs")

    def test_command_add_error(self):
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "ia", add=True)

    def test_command_mt(self):
        call_command("auto_translate", "--mt", "weblate", "test", "test", "cs")

    def test_command_mt_error(self):
        with self.assertRaises(CommandError):
            call_command("auto_translate", "--mt", "invalid", "test", "test", "ia")
        with self.assertRaises(CommandError):
            call_command(
                "auto_translate", "--threshold", "invalid", "test", "test", "ia"
            )

    def test_command_add(self):
        self.component.file_format = "po"
        self.component.new_lang = "add"
        self.component.new_base = "po/cs.po"
        self.component.clean()
        self.component.save()
        call_command("auto_translate", "test", "test", "ia", add=True)
        self.assertTrue(
            self.component.translation_set.filter(language__code="ia").exists()
        )

    def test_command_different(self):
        self.make_different()
        call_command("auto_translate", "test", "test-2", "cs", source="test/test")

    def test_command_errors(self):
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "cs", user="invalid")
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "cs", source="invalid")
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "cs", source="test/invalid")
        with self.assertRaises(CommandError):
            call_command("auto_translate", "test", "test", "xxx")


class AutoTranslationMtTest(ViewTestCase):
    @classmethod
    def _databases_support_transactions(cls):
        # This is workaroud for MySQL as FULL TEXT index does not work
        # well inside a transaction, so we avoid using transactions for
        # tests. Otherwise we end up with no matches for the query.
        # See https://dev.mysql.com/doc/refman/5.6/en/innodb-fulltext-index.html
        if not using_postgresql():
            return False
        return super()._databases_support_transactions()

    def setUp(self):
        super().setUp()
        # Need extra power
        self.user.is_superuser = True
        self.user.save()
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

    def test_none(self):
        """Test for automatic translation with no content."""
        url = reverse("auto_translation", kwargs=self.kw_translation)
        response = self.client.post(url)
        self.assertRedirects(response, self.translation_url)

    def make_different(self):
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")

    def perform_auto(self, expected=1, **kwargs):
        self.make_different()
        params = {"project": "test", "lang": "cs", "component": "test-3"}
        url = reverse("auto_translation", kwargs=params)
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

        self.assertRedirects(response, reverse("translation", kwargs=params))
        # Check we've translated something
        translation = self.component3.translation_set.get(language_code="cs")
        translation.invalidate_cache()
        self.assertEqual(translation.stats.translated, expected)

    def test_different(self):
        """Test for automatic translation with different content."""
        self.perform_auto(engines=["weblate"], threshold=80)

    def test_inconsistent(self):
        self.perform_auto(
            0, filter_type="check:inconsistent", engines=["weblate"], threshold=80
        )

    def test_overwrite(self):
        self.perform_auto(overwrite="1", engines=["weblate"], threshold=80)
