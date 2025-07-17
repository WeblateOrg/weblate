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
from weblate.memory.tasks import (
    handle_unit_translation_change,
    import_memory,
)
from weblate.memory.utils import CATEGORY_FILE
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.db import TransactionsTestMixin
from weblate.utils.hash import hash_to_checksum
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
        status=Memory.STATUS_ACTIVE,
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
                    "status": 1,
                    "context": "",
                }
            ],
        )

    def test_import_invalid_command(self) -> None:
        # try uploading an unsupported format
        with self.assertRaises(CommandError):
            call_command("import_memory", get_test_file("strings.xml"))
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

    def import_file_with_languages_test(
        self,
        filename: str,
        source_language: str,
        target_language: str,
        expected_result: int,
    ) -> None:
        """Test memory file upload requiring source and target languages."""
        # check source and target languages are required
        with self.assertRaises(CommandError):
            call_command("import_memory", get_test_file(filename))
        self.assertEqual(Memory.objects.count(), 0)

        with self.assertRaises(CommandError):
            call_command(
                "import_memory",
                get_test_file(filename),
                source_language=source_language,
            )
        self.assertEqual(Memory.objects.count(), 0)

        with self.assertRaises(CommandError):
            call_command(
                "import_memory",
                get_test_file(filename),
                target_language=target_language,
            )
        self.assertEqual(Memory.objects.count(), 0)

        #  check unknown languages raise Error
        with self.assertRaises(CommandError):
            call_command(
                "import_memory",
                get_test_file(filename),
                source_language=source_language,
                target_language="zzz",
            )
        self.assertEqual(Memory.objects.count(), 0)

        # successful import
        call_command(
            "import_memory",
            get_test_file(filename),
            source_language="en",
            target_language="cs",
        )
        self.assertEqual(Memory.objects.count(), expected_result)

    def test_import_xliff(self) -> None:
        """Test the import of an XLIFF file."""
        with self.assertRaises(CommandError):
            # no valid entries, only source strings
            call_command(
                "import_memory",
                get_test_file("cs.xliff"),
                source_language="en",
                target_language="cs",
            )

        self.assertEqual(Memory.objects.count(), 0)

        self.import_file_with_languages_test("ids-translated.xliff", "en", "cs", 2)

    def test_import_po(self) -> None:
        """Test the import of an GNU PO file."""
        self.import_file_with_languages_test("cs.po", "en", "cs", 1)

    def test_import_unsupported_format(self) -> None:
        """Test the import of an unsupported file."""
        with self.assertRaises(CommandError):
            self.import_file_with_languages_test("cs.ts", "en", "cs", 0)

    def test_import_project(self) -> None:
        import_memory(self.project.id)
        self.assertEqual(Memory.objects.count(), 4)
        import_memory(self.project.id)
        self.assertEqual(Memory.objects.count(), 4)

    def test_user_contribute_personal_tm(self) -> None:
        self.user.profile.contribute_personal_tm = False
        self.user.profile.save()

        unit = self.get_unit()
        unit.translate(self.user, "Nazdar", STATE_TRANSLATED)
        self.assertEqual(Memory.objects.count(), 2)

        self.user.profile.contribute_personal_tm = True
        self.user.profile.save()
        # enabling personal translation memory doesn't add previously
        # translated units to memory
        self.assertEqual(Memory.objects.count(), 2)

    def test_component_contribute_project_tm(self) -> None:
        unit = self.get_unit()
        component = unit.translation.component
        component.contribute_project_tm = False
        component.save()

        unit = self.get_unit()
        unit.translate(self.user, "Nazdar", STATE_TRANSLATED)
        # hello, world! unit X 2 (user memory and shared memory)
        self.assertEqual(Memory.objects.count(), 2)

        component.contribute_project_tm = True
        component.save()
        # hello, world! unit X 3 (user, project and shared memory)
        # + other units (try weblate string) in the components
        # 2 translations X 2 (project and shared memory) = total 7
        self.assertEqual(Memory.objects.count(), 7)

    def test_import_unit(self) -> None:
        unit = self.get_unit()
        handle_unit_translation_change(unit, self.user)
        self.assertEqual(Memory.objects.count(), 0)
        handle_unit_translation_change(unit, self.user)
        self.assertEqual(Memory.objects.count(), 0)
        unit.translate(self.user, "Nazdar", STATE_TRANSLATED)
        self.assertEqual(Memory.objects.count(), 3)
        Memory.objects.all().delete()
        handle_unit_translation_change(unit, self.user)
        self.assertEqual(Memory.objects.count(), 3)
        handle_unit_translation_change(unit, self.user)
        self.assertEqual(Memory.objects.count(), 3)

    def test_memory_status_no_review(self) -> None:
        self.test_memory_status_with_review(translation_review=False)

    def test_memory_status_with_review(self, translation_review: bool = True) -> None:
        self.project.translation_review = translation_review
        self.project.save()
        machine_translation = WeblateMemory({})

        unit = self.get_unit()
        unit.translate(self.user, "Hello", STATE_TRANSLATED)

        # check memory status is created with status pending
        expected_status = (
            Memory.STATUS_PENDING if translation_review else Memory.STATUS_ACTIVE
        )
        self.assertEqual(
            1,
            Memory.objects.filter(project=self.project, status=expected_status).count(),
        )

        suggestion = machine_translation.search(unit, "Hello, world!\n", None)[0]
        if translation_review:
            # quality is less than 100% because of penalty
            self.assertLess(suggestion["quality"], 100)
        else:
            self.assertEqual(suggestion["quality"], 100)

        if translation_review:
            self.approve_translation(unit, "Hello")

            # check that memory status is updated to active
            self.assertEqual(
                1,
                Memory.objects.filter(
                    project=self.project, status=Memory.STATUS_ACTIVE
                ).count(),
            )
            suggestion = machine_translation.search(unit, "Hello, world!\n", None)[0]
            self.assertEqual(suggestion["quality"], 100)

            # mark the translation as needing editing
            self.approve_translation(unit, "Hello", review="10")

            # check that memory status is updated to pending
            self.assertEqual(
                1,
                Memory.objects.filter(
                    project=self.project, status=Memory.STATUS_PENDING
                ).count(),
            )
            suggestion = machine_translation.search(unit, "Hello, world!\n", None)[0]
            self.assertLess(suggestion["quality"], 100)

    def approve_translation(self, unit, target: str, review: str = "30"):
        # allow user to approve translations
        self.project.add_user(self.user, "Administration")
        params = {
            "checksum": unit.checksum,
            "contentsum": hash_to_checksum(unit.content_hash),
            "translationsum": hash_to_checksum(unit.get_target_hash()),
            "target_0": target,
            "review": review,
        }
        self.client.post(unit.translation.get_translate_url(), params, follow=True)

    def test_pending_memory_autoclean(self, autoclean_active: bool = False) -> None:
        import_memory(self.project.id)
        imported_memory_ids = [m.pk for m in Memory.objects.all()]
        initial_memory_count = len(imported_memory_ids)
        not_imported_memory_qs = Memory.objects.exclude(id__in=imported_memory_ids)

        # create a translation with review enabled
        self.project.translation_review = True
        self.project.save()
        machine_translation = WeblateMemory({})

        unit = self.get_unit()
        unit.translate(self.user, "Hello 1", STATE_TRANSLATED)

        # check memory status is created with status pending
        self.assertEqual(
            1,
            not_imported_memory_qs.filter(
                project=self.project, context=unit.context, status=Memory.STATUS_PENDING
            ).count(),
        )

        # check that suggestion quality is less than 100% because of penalty
        suggestion = machine_translation.search(unit, "Hello, world!\n", None)[0]
        self.assertLess(suggestion["quality"], 100)

        # another user submits a translation
        unit.translate(self.anotheruser, "Hello 2", STATE_TRANSLATED)
        self.assertEqual(
            2,
            not_imported_memory_qs.filter(
                project=self.project, context=unit.context, status=Memory.STATUS_PENDING
            ).count(),
        )
        for suggestion in machine_translation.search(unit, "Hello, world!\n", None):
            self.assertLess(suggestion["quality"], 100)

        # approve one translation, check that only 1 memory left with status active
        self.approve_translation(unit, "Hello 1")

        self.assertEqual(
            1,
            not_imported_memory_qs.filter(
                project=self.project, context=unit.context, status=Memory.STATUS_ACTIVE
            ).count(),
        )
        suggestion = machine_translation.search(unit, "Hello, world!\n", None)[0]
        self.assertEqual(suggestion["quality"], 100)

        if not autoclean_active:
            # check that the other pending memory has not been deleted
            self.assertEqual(
                1,
                not_imported_memory_qs.filter(
                    project=self.project,
                    context=unit.context,
                    status=Memory.STATUS_PENDING,
                ).count(),
            )
            for suggestion in machine_translation.search(unit, "Hello, world!\n", None):
                if suggestion["text"] == "Hello 2\n":  # ignore imported entries
                    self.assertLess(suggestion["quality"], 100)

        # check that imported memory entries were not affected by autoclean
        self.assertEqual(
            initial_memory_count,
            Memory.objects.filter(pk__in=imported_memory_ids).count(),
        )

    def test_pending_memory_autoclean_active(self) -> None:
        self.project.autoclean_tm = True
        self.project.save()
        self.test_pending_memory_autoclean(autoclean_active=True)

    def test_clean_memory_command(
        self, autoclean_tm: bool = False, translation_review: bool = False
    ) -> None:
        self.project.autoclean_tm = autoclean_tm
        self.project.save()

        import_memory(self.project.id)
        excepted_deleted_count = 0

        unit = self.get_unit()

        self.project.translation_review = translation_review
        self.project.save()

        unit.translate(self.user, "Hello 1", STATE_TRANSLATED)
        unit.translate(self.anotheruser, "Hello 2", STATE_TRANSLATED)

        if translation_review:
            self.approve_translation(unit, "Hello 1")
            if not autoclean_tm:
                excepted_deleted_count += 3  # 1 for each [project, user, shared]

        total_memory_count = Memory.objects.count()
        call_command("cleanup_memory")
        self.assertEqual(
            Memory.objects.all().count(), total_memory_count - excepted_deleted_count
        )

    def test_clean_memory_command_with_translation_review_no_autoclean(self) -> None:
        self.test_clean_memory_command(autoclean_tm=False, translation_review=True)

    def test_clean_memory_command_with_translation_review_and_autoclean(self) -> None:
        self.test_clean_memory_command(autoclean_tm=True, translation_review=True)

    def test_clean_memory_command_no_translation_review_with_autoclean(self) -> None:
        self.test_clean_memory_command(autoclean_tm=True, translation_review=False)

    def test_memory_context(
        self, autoclean_tm: bool = False, translation_review: bool = False
    ) -> None:
        self.project.translation_review = translation_review
        self.project.autoclean_tm = autoclean_tm
        self.project.save()
        machine_translation = WeblateMemory({})

        # check that quality of suggestion is inferior if contexts differ
        unit = self.get_unit()
        unit2 = self.translation.unit_set.create(
            context="Different context",
            source=unit.source,
            source_unit=unit.source_unit,
            id_hash=1001,
            position=1001,
        )
        unit.translate(self.user, "Hello no context", STATE_TRANSLATED)
        unit2.translate(self.user, "Hello with context", STATE_TRANSLATED)

        if translation_review:
            self.approve_translation(unit, "Hello no context")
            self.approve_translation(unit2, "Hello with context")

        suggestions = machine_translation.search(unit, unit.source, None)
        with_context = [s for s in suggestions if "Hello with context" in s["text"]][0]  # noqa: RUF015
        no_context = [s for s in suggestions if "Hello no context" in s["text"]][0]  # noqa: RUF015
        self.assertLess(with_context["quality"], no_context["quality"])

        # check that memory with different context is not affected by autoclean
        if autoclean_tm:
            unit.translate(self.user, "New translation", STATE_TRANSLATED)
            self.approve_translation(unit, "New translation")
            suggestions = machine_translation.search(unit, unit.source, None)

            self.assertFalse(
                [s for s in suggestions if "Hello no context" in s["text"]]
            )
            self.assertTrue([s for s in suggestions if "New translation" in s["text"]])
            self.assertTrue(
                [s for s in suggestions if "Hello with context" in s["text"]]
            )

    def test_memory_context_with_review_no_autoclean(self):
        self.test_memory_context(False, True)

    def test_memory_context_with_review_and_autoclean(self):
        self.test_memory_context(True, True)

    def test_memory_context_no_review_with_autoclean(self):
        self.test_memory_context(True, False)


class MemoryViewTest(FixtureTestCase):
    def upload_file(
        self,
        name,
        prefix: str = "",
        source_language: Language | None = None,
        target_language: Language | None = None,
        **kwargs,
    ):
        with open(get_test_file(name), "rb") as handle:
            data = {"file": handle}
            if source_language:
                data |= {"source_language": source_language}
            if target_language:
                data |= {"target_language": target_language}

            return self.client.post(
                reverse(f"{prefix}memory-upload", **kwargs),
                data,
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

        # Test upload a file that requires source and target languages
        response = self.upload_file("ids-translated.xliff", **kwargs)
        self.assertContains(
            response,
            "Source language and target language must be specified for this file format",
        )

        en = Language.objects.get(code="en")
        cs = Language.objects.get(code="cs")
        response = self.upload_file(
            "ids-translated.xliff",
            source_language=en.id,
            target_language=cs.id,
            **kwargs,
        )
        if fail:
            self.assertContains(response, "Permission Denied", status_code=403)
        else:
            self.assertContains(response, "File processed")

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

    def test_upload_unsupported_file(self) -> None:
        response = self.upload_file("cs.ts")
        self.assertContains(
            response, "Error in parameter file: File extension “ts” is not allowed."
        )
        self.assertContains(
            response, "Allowed extensions are: json, tmx, xliff, po, csv."
        )


class ThresholdTestCase(SimpleTestCase):
    def test_search(self) -> None:
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x", 10), 0.7, delta=0.01
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 50, 10), 0.73, delta=0.01
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 500, 10), 0.76, delta=0.01
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("<" * 50 + "x" * 50 + ">" * 50, 10),
            0.73,
            delta=0.01,
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("🩸", 10),
            0.7,
            delta=0.01,
        )

    def test_auto(self) -> None:
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x", 80), 0.96, delta=0.01
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 50, 80), 0.96, delta=0.01
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 500, 80), 0.98, delta=0.01
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("<" * 50 + "x" * 50 + ">" * 50, 80),
            0.96,
            delta=0.01,
        )

    def test_machine(self) -> None:
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x", 75), 0.95, delta=0.01
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 50, 75), 0.96, delta=0.01
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 500, 75), 0.97, delta=0.01
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("<" * 50 + "x" * 50 + ">" * 50, 75),
            0.96,
            delta=0.01,
        )

    def test_machine_exact(self) -> None:
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x", 100), 1.0, delta=0.01
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 50, 100), 1.0, delta=0.01
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("x" * 500, 100), 1.0, delta=0.01
        )
        self.assertAlmostEqual(
            Memory.objects.threshold_to_similarity("<" * 50 + "x" * 50 + ">" * 50, 100),
            1.0,
            delta=0.01,
        )
