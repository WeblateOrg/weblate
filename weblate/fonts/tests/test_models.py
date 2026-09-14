# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from importlib import import_module

from django.apps import apps
from django.core.exceptions import ValidationError

from weblate.fonts.models import FONT_STORAGE, Font, FontGroup, FontOverride
from weblate.fonts.tasks import cleanup_font_files
from weblate.fonts.tests.utils import FontComponentTestCase
from weblate.trans.models import Project


class FontModelTest(FontComponentTestCase):
    def test_save(self) -> None:
        font = self.add_font()
        self.assertEqual(font.family, "Kurinto Sans")
        self.assertEqual(font.style, "Regular")

    def assert_font_files(self, expected: int) -> None:
        result = 0
        excluded = {".uuid"}
        for name in FONT_STORAGE.listdir(".")[1]:
            if name not in excluded:
                result += 1
        self.assertEqual(result, expected)

    def test_cleanup(self) -> None:
        cleanup_font_files()
        self.assert_font_files(0)
        font = self.add_font()
        self.assert_font_files(1)
        cleanup_font_files()
        self.assert_font_files(1)
        font.delete()
        self.assert_font_files(1)
        cleanup_font_files()
        self.assert_font_files(0)

    def test_override_project_scope(self) -> None:
        local_font = self.add_font()
        private_project = Project.objects.create(name="Private", slug="private")
        private_font = Font.objects.create(
            family="Private font",
            style="Regular",
            font=local_font.font.name,
            project=private_project,
            user=self.user,
        )
        group = FontGroup.objects.create(
            name="font-group", font=local_font, project=self.project
        )

        with self.assertRaisesMessage(
            ValidationError, "Font has to be in the same project as the font group."
        ):
            FontOverride.objects.create(
                group=group,
                language=self.translation.language,
                font=private_font,
            )

    def test_remove_cross_project_font_overrides(self) -> None:
        local_font = self.add_font()
        private_project = Project.objects.create(name="Private", slug="private")
        private_font = Font.objects.create(
            family="Private font",
            style="Regular",
            font=local_font.font.name,
            project=private_project,
            user=self.user,
        )
        group = FontGroup.objects.create(
            name="font-group", font=local_font, project=self.project
        )
        override = FontOverride.objects.create(
            group=group,
            language=self.translation.language,
            font=local_font,
        )
        FontOverride.objects.filter(pk=override.pk).update(font=private_font)

        migration = import_module(
            "weblate.fonts.migrations.0002_remove_cross_project_font_overrides"
        )
        migration.remove_cross_project_font_overrides(apps, None)

        self.assertFalse(FontOverride.objects.filter(pk=override.pk).exists())
