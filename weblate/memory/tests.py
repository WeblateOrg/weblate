# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase
from django.urls import reverse
from jsonschema import validate
from weblate_schemas import load_schema

from weblate.lang.models import Language
from weblate.memory.machine import WeblateMemory
from weblate.memory.models import Memory
from weblate.memory.tasks import handle_unit_translation_change, import_memory
from weblate.memory.utils import CATEGORY_FILE
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.db import TransactionsTestMixin
from weblate.utils.state import STATE_TRANSLATED


def add_document() -> None:
    Memory.objects.create(
        source_language=Language.objects.get(code="en"),
        target_language=Language.objects.get(code="cs"),
        source="Hello",
        target="Ahoj",
        origin="test",
        from_file=True,
        shared=False,
    )


class MemoryModelTest(TransactionsTestMixin, FixtureTestCase):
    def test_machine(self) -> None:
        add_document()
        unit = self.get_unit()
        machine_translation = WeblateMemory({})
        self.assertEqual(
            machine_translation.search(unit, "Hello", None),
            [
                {
                    "quality": 100,
                    "service": "Weblate Translation Memory",
                    "origin": "File: test",
                    "source": "Hello",
                    "text": "Ahoj",
                    "original_source": "Hello",
                    "show_quality": True,
                    "delete_url": None,
                }
            ],
        )

        self.user.is_superuser = True
        self.user.save()
        self.assertEqual(
            machine_translation.search(unit, "Hello", self.user),
            [
                {
                    "quality": 100,
                    "service": "Weblate Translation Memory",
                    "origin": "File: test",
                    "source": "Hello",
                    "original_source": "Hello",
                    "text": "Ahoj",
                    "show_quality": True,
                    "delete_url": f"/api/memory/{Memory.objects.all()[0].pk}/",
                }
            ],
        )

    def test_machine_batch(self) -> None:
        add_document()
        unit = self.get_unit()
        machine_translation = WeblateMemory({})
        unit.source = "Hello"
        machine_translation.batch_translate([unit])
        machinery = unit.machinery
        del machinery["origin"]
        self.assertEqual(machinery, {"quality": [100], "translation": ["Ahoj"]})

    def test_import_tmx_command(self) -> None:
        call_command("import_memory", get_test_file("memory.tmx"))
        self.assertEqual(Memory.objects.count(), 2)

    def test_import_tmx2_command(self) -> None:
        call_command("import_memory", get_test_file("memory2.tmx"))
        self.assertEqual(Memory.objects.count(), 1)

    def test_import_map(self) -> None:
        call_command(
            "import_memory", get_test_file("memory.tmx"), language_map="en_US:en"
        )
        self.assertEqual(Memory.objects.count(), 2)

    def test_dump_command(self) -> None:
        add_document()
        output = StringIO()
        call_command("dump_memory", stdout=output)
        data = json.loads(output.getvalue())
        validate(data, load_schema("weblate-memory.schema.json"))
        self.assertEqual(
            data,
            [
                {
                    "source_language": "en",
                    "target_language": "cs",
                    "source": "Hello",
                    "target": "Ahoj",
                    "origin": "test",
                    "category": CATEGORY_FILE,
                }
            ],
        )

    def test_import_invalid_command(self) -> None:
        with self.assertRaises(CommandError):
            call_command("import_memory", get_test_file("cs.po"))
        self.assertEqual(Memory.objects.count(), 0)

    def test_import_json_command(self) -> None:
        call_command("import_memory", get_test_file("memory.json"))
        self.assertEqual(Memory.objects.count(), 1)

    def test_import_broken_json_command(self) -> None:
        with self.assertRaises(CommandError):
            call_command("import_memory", get_test_file("memory-broken.json"))
        self.assertEqual(Memory.objects.count(), 0)

    def test_import_empty_json_command(self) -> None:
        with self.assertRaises(CommandError):
            call_command("import_memory", get_test_file("memory-empty.json"))
        self.assertEqual(Memory.objects.count(), 0)

    def test_import_project(self) -> None:
        import_memory(self.project.id)
        self.assertEqual(Memory.objects.count(), 4)
        import_memory(self.project.id)
        self.assertEqual(Memory.objects.count(), 4)

    def test_import_unit(self) -> None:
        unit = self.get_unit()
        handle_unit_translation_change(unit.id, self.user.id)
        self.assertEqual(Memory.objects.count(), 0)
        handle_unit_translation_change(unit.id, self.user.id)
        self.assertEqual(Memory.objects.count(), 0)
        unit.translate(self.user, "Nazdar", STATE_TRANSLATED)
        self.assertEqual(Memory.objects.count(), 3)
        Memory.objects.all().delete()
        handle_unit_translation_change(unit.id, self.user.id)
        self.assertEqual(Memory.objects.count(), 3)
        handle_unit_translation_change(unit.id, self.user.id)
        self.assertEqual(Memory.objects.count(), 3)


class MemoryViewTest(FixtureTestCase):
    def upload_file(self, name, prefix: str = "", **kwargs):
        with open(get_test_file(name), "rb") as handle:
            return self.client.post(
                reverse(f"{prefix}memory-upload", **kwargs),
                {"file": handle},
                follow=True,
            )

    def test_memory(
        self, match="Number of your entries", fail=False, prefix: str = "", **kwargs
    ) -> None:
        is_project_scoped = "kwargs" in kwargs and "project" in kwargs["kwargs"]
        # Test wipe without confirmation
        response = self.client.get(reverse(f"{prefix}memory-delete", **kwargs))
        self.assertRedirects(response, reverse(f"{prefix}memory", **kwargs))

        response = self.client.post(reverse(f"{prefix}memory-delete", **kwargs))
        self.assertRedirects(response, reverse(f"{prefix}memory", **kwargs))

        # Test rebuild without confirmation
        if is_project_scoped:
            response = self.client.get(reverse(f"{prefix}memory-rebuild", **kwargs))
            self.assertRedirects(response, reverse(f"{prefix}memory", **kwargs))

        # Test list
        response = self.client.get(reverse(f"{prefix}memory", **kwargs))
        self.assertContains(response, match)

        # Test upload
        response = self.upload_file("memory.tmx", prefix=prefix, **kwargs)
        if fail:
            self.assertContains(response, "Permission Denied", status_code=403)
        else:
            self.assertContains(response, "File processed")

        # Test download
        response = self.client.get(reverse(f"{prefix}memory-download", **kwargs))
        validate(response.json(), load_schema("weblate-memory.schema.json"))

        # Test download
        response = self.client.get(
            reverse(f"{prefix}memory-download", **kwargs), {"format": "tmx"}
        )
        self.assertContains(response, "<tmx")
        response = self.client.get(
            reverse(f"{prefix}memory-download", **kwargs),
            {"format": "tmx", "origin": "memory.tmx"},
        )
        self.assertContains(response, "<tmx")
        response = self.client.get(
            reverse(f"{prefix}memory-download", **kwargs), {"format": "json"}
        )
        validate(response.json(), load_schema("weblate-memory.schema.json"))

        # Test wipe
        count = Memory.objects.count()
        response = self.client.post(
            reverse(f"{prefix}memory-delete", **kwargs),
            {"confirm": "1", "origin": "invalid"},
            follow=True,
        )
        if fail:
            self.assertContains(response, "Permission Denied", status_code=403)
        else:
            self.assertContains(response, "Entries were deleted")
            self.assertEqual(count, Memory.objects.count())
            response = self.client.post(
                reverse(f"{prefix}memory-delete", **kwargs),
                {"confirm": "1"},
                follow=True,
            )
            self.assertContains(response, "Entries were deleted")
            self.assertGreater(count, Memory.objects.count())

        # Test rebuild
        if is_project_scoped:
            response = self.client.post(
                reverse(f"{prefix}memory-rebuild", **kwargs),
                {"confirm": "1", "origin": "invalid"},
                follow=True,
            )
            self.assertContains(response, "Permission Denied", status_code=403)
            response = self.client.post(
                reverse(f"{prefix}memory-rebuild", **kwargs),
                {"confirm": "1", "origin": self.component.full_slug},
                follow=True,
            )
            if fail:
                self.assertContains(response, "Permission Denied", status_code=403)
            else:
                self.assertContains(
                    response, "Entries were deleted and the translation memory"
                )
                self.assertEqual(4, Memory.objects.count())
                response = self.client.post(
                    reverse(f"{prefix}memory-rebuild", **kwargs),
                    {"confirm": "1"},
                    follow=True,
                )
                self.assertContains(
                    response, "Entries were deleted and the translation memory"
                )
                self.assertEqual(4, Memory.objects.count())

        # Test invalid upload
        response = self.upload_file("cs.json", **kwargs)
        if fail:
            self.assertContains(response, "Permission Denied", status_code=403)
        else:
            self.assertContains(response, "Could not parse JSON file")

        # Test invalid upload
        response = self.upload_file("memory-broken.json", **kwargs)
        if fail:
            self.assertContains(response, "Permission Denied", status_code=403)
        else:
            self.assertContains(response, "Could not parse JSON file")

        # Test invalid upload
        response = self.upload_file("memory-invalid.json", **kwargs)
        if fail:
            self.assertContains(response, "Permission Denied", status_code=403)
        else:
            self.assertContains(response, "Could not parse JSON file")

    def test_memory_project(self) -> None:
        self.test_memory("Number of entries for Test", True, kwargs=self.kw_project)

    def test_memory_project_superuser(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        self.test_memory("Number of entries for Test", False, kwargs=self.kw_project)

    def test_global_memory_superuser(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        self.test_memory("Number of uploaded shared entries", False, prefix="manage-")
        # Download all entries
        response = self.client.get(
            reverse("manage-memory-download"),
            {"format": "json", "kind": "all"},
        )
        validate(response.json(), load_schema("weblate-memory.schema.json"))
        # Download shared entries
        response = self.client.get(
            reverse("manage-memory-download"),
            {"format": "json", "kind": "shared"},
        )
        validate(response.json(), load_schema("weblate-memory.schema.json"))


class ThresholdTestCase(SimpleTestCase):
    def test_search(self) -> None:
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x", 10), 0.66, delta=0.006
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 50, 10), 0.71, delta=0.006
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 500, 10), 0.74, delta=0.006
        )

    def test_auto(self) -> None:
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x", 80), 0.97, delta=0.006
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 50, 80), 0.98, delta=0.006
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 500, 80), 0.98, delta=0.006
        )

    def test_machine(self) -> None:
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x", 75), 0.96, delta=0.006
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 50, 75), 0.97, delta=0.006
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 500, 75), 0.97, delta=0.006
        )

    def test_machine_exact(self) -> None:
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x", 100), 1.0, delta=0.006
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 50, 100), 1.0, delta=0.006
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 500, 100), 1.0, delta=0.006
        )
