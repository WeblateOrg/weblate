# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.storage import InMemoryStorage
from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.fonts.apps import check_font_storage
from weblate.fonts.models import Font, FontGroup, FontOverride
from weblate.fonts.storage import font_storage
from weblate.fonts.tasks import cleanup_font_files
from weblate.fonts.tests.utils import FONT, FONT_BOLD, FontComponentTestCase
from weblate.trans.models import Project
from weblate.utils.data import data_dir


class FontModelTest(FontComponentTestCase):
    def test_save(self) -> None:
        font = self.add_font()
        self.assertEqual(font.family, "Kurinto Sans")
        self.assertEqual(font.style, "Regular")

    def assert_font_files(self, expected: int) -> None:
        result = 0
        excluded = {".uuid"}
        try:
            files = font_storage.listdir("")[1]
        except FileNotFoundError:
            files = []
        for name in files:
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

    def test_replace(self) -> None:
        font = self.add_font()
        name = font.font.name
        assert name is not None
        original_path = font.get_local_path()
        # Replace the content under the same name, as storage that overwrites
        # files does
        font_storage.delete(name)
        with FONT_BOLD.open("rb") as handle:
            font.font.save(name, File(handle))
        self.assertEqual(font.font.name, name)
        # The local copy follows the replaced font file
        self.assertNotEqual(font.get_local_path(), original_path)
        self.assertEqual(
            Path(font.get_local_path()).read_bytes(), FONT_BOLD.read_bytes()
        )

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


@override_settings(
    STORAGES={
        **settings.STORAGES,
        "fonts": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    }
)
class FontStorageTest(FontComponentTestCase):
    def test_storage(self) -> None:
        font = self.add_font()
        self.assertIsInstance(font.font.storage, InMemoryStorage)
        self.assertEqual(Path(font.get_local_path()).read_bytes(), FONT.read_bytes())

    def test_cleanup(self) -> None:
        with FONT.open("rb") as handle:
            name = font_storage.save("stale.ttf", handle)
        cleanup_font_files()
        self.assertFalse(font_storage.exists(name))


class FontStorageCheckTest(SimpleTestCase):
    def check_storage(self, options: dict[str, object]) -> list[str]:
        with override_settings(
            STORAGES={
                **settings.STORAGES,
                "fonts": {
                    "BACKEND": "storages.backends.s3.S3Storage",
                    "OPTIONS": {"bucket_name": "weblate", **options},
                },
            }
        ):
            return [
                message.id or ""
                for message in check_font_storage(app_configs=None, databases=None)
            ]

    def test_default(self) -> None:
        self.assertEqual(list(check_font_storage(app_configs=None, databases=None)), [])
        # Existing installations keep fonts in DATA_DIR
        self.assertEqual(
            font_storage.path("font.ttf"), str(Path(data_dir("fonts"), "font.ttf"))
        )

    def test_overwrite(self) -> None:
        # django-storages overwrites files by default
        self.assertEqual(self.check_storage({}), ["weblate.W054"])
        self.assertEqual(self.check_storage({"file_overwrite": False}), [])
