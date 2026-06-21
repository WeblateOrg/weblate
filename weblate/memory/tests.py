# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import MagicMock, call, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.models import Q
from django.db.models.functions import MD5
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import reverse
from jsonschema import validate
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from weblate_schemas import load_schema

from weblate.lang.data import FORMULA_WITH_ZERO
from weblate.lang.models import Language, Plural
from weblate.memory.machine import WeblateMemory
from weblate.memory.models import (
    Memory,
    MemoryImportError,
    MemoryQuerySet,
    load_memory_json_data,
    load_memory_tmx_store,
)
from weblate.memory.tasks import (
    MEMORY_UPDATE_LOOKUP_CHUNK_SIZE,
    get_group_matching_memory,
    handle_unit_translation_change,
    import_memory,
)
from weblate.memory.utils import CATEGORY_FILE
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import get_test_file
from weblate.utils.hash import hash_to_checksum
from weblate.utils.state import STATE_TRANSLATED

if TYPE_CHECKING:
    from weblate.memory.tasks import MemoryGroupEntry


def add_document(source: str = "Hello", target: str = "Ahoj") -> None:
    Memory.objects.create(
        source_language=Language.objects.get(code="en"),
        target_language=Language.objects.get(code="cs"),
        source=source,
        target=target,
        origin="test",
        from_file=True,
        shared=False,
        status=Memory.STATUS_ACTIVE,
    )


class MemoryParserTest(SimpleTestCase):
    def test_load_memory_json_data(self) -> None:
        data = load_memory_json_data(Path(get_test_file("memory.json")).read_bytes())

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["source"], "Hello")

    def test_load_memory_json_data_invalid_schema(self) -> None:
        with self.assertRaises(JSONSchemaValidationError):
            load_memory_json_data(
                Path(get_test_file("memory-invalid.json")).read_bytes()
            )

    def test_load_memory_tmx_store(self) -> None:
        store = load_memory_tmx_store(
            BytesIO(Path(get_test_file("memory.tmx")).read_bytes())
        )

        self.assertEqual(len(list(store.units)), 1)

    def test_import_tmx_missing_header(self) -> None:
        with self.assertRaisesMessage(
            MemoryImportError, "Header missing in the TMX file!"
        ):
            Memory.objects.import_tmx(
                request=None,
                fileobj=BytesIO(
                    b"""<?xml version="1.0" encoding="UTF-8"?>
<tmx version="1.4">
  <body>
    <tu>
      <tuv xml:lang="en"><seg>Hello</seg></tuv>
      <tuv xml:lang="cs"><seg>Ahoj</seg></tuv>
    </tu>
  </body>
</tmx>
"""
                ),
                origin="missing-header.tmx",
            )

    def test_bulk_matching_memory_uses_exact_md5_pairs(self) -> None:
        entries = [
            self.get_memory_group_entry(0, "source 1", "target 1"),
            self.get_memory_group_entry(1, "source 2", "target 2"),
        ]
        statuses = {key: status for _, key, _, status in entries}
        exact_match = self.get_matching_memory("source 1", "target 1")
        cross_pair = self.get_matching_memory("source 1", "target 2")

        with patch.object(
            Memory.objects, "filter", return_value=[exact_match, cross_pair]
        ) as filter_mock:
            existing, to_update = get_group_matching_memory(
                ("origin", 1, 2), entries, statuses
            )

        args, kwargs = filter_mock.call_args
        self.assertNotIn("source__in", kwargs)
        self.assertNotIn("target__in", kwargs)
        self.assertEqual(
            set(kwargs),
            {
                "from_file",
                "origin__md5",
                "source_language_id",
                "target_language_id",
            },
        )
        self.assertEqual(kwargs["from_file"], False)
        self.assertEqual(kwargs["source_language_id"], 1)
        self.assertEqual(kwargs["target_language_id"], 2)
        self.assert_md5_value(kwargs["origin__md5"], "origin")
        self.assertEqual(
            self.get_query_pairs(args[0]),
            {("source 1", "target 1"), ("source 2", "target 2")},
        )
        self.assertEqual(
            existing["origin", 1, 2, "source 1", "target 1"], {("project", 1)}
        )
        self.assertNotIn(
            ("project", 1), existing["origin", 1, 2, "source 1", "target 2"]
        )
        self.assertEqual(to_update, [exact_match])

    def test_bulk_matching_memory_chunks_exact_md5_pairs(self) -> None:
        entries = [
            self.get_memory_group_entry(position, f"source {position}", "target")
            for position in range(MEMORY_UPDATE_LOOKUP_CHUNK_SIZE + 1)
        ]
        statuses = {key: status for _, key, _, status in entries}

        with patch.object(Memory.objects, "filter", return_value=[]) as filter_mock:
            get_group_matching_memory(("origin", 1, 2), entries, statuses)

        self.assertEqual(filter_mock.call_count, 2)
        first_args, first_kwargs = filter_mock.call_args_list[0]
        second_args, second_kwargs = filter_mock.call_args_list[1]
        self.assertEqual(
            len(self.get_query_pairs(first_args[0])), MEMORY_UPDATE_LOOKUP_CHUNK_SIZE
        )
        self.assertEqual(len(self.get_query_pairs(second_args[0])), 1)
        self.assert_md5_value(first_kwargs["origin__md5"], "origin")
        self.assert_md5_value(second_kwargs["origin__md5"], "origin")

    def get_memory_group_entry(
        self, position: int, source: str, target: str
    ) -> MemoryGroupEntry:
        return (
            position,
            ("origin", 1, 2, source, target),
            {
                "source_language_id": 1,
                "target_language_id": 2,
                "source": source,
                "context": "",
                "target": target,
                "origin": "origin",
                "add_shared": False,
                "add_project": True,
                "add_user": False,
                "user_id": None,
                "project_id": 1,
                "unit_state": STATE_TRANSLATED,
            },
            Memory.STATUS_ACTIVE,
        )

    def get_matching_memory(self, source: str, target: str) -> MagicMock:
        return MagicMock(
            origin="origin",
            source_language_id=1,
            target_language_id=2,
            source=source,
            target=target,
            status=Memory.STATUS_PENDING,
            user_id=None,
            project_id=1,
            shared=False,
        )

    def get_query_pairs(self, query: Q) -> set[tuple[str, str]]:
        children = query.children if query.connector == "OR" else [query]
        pairs = set()
        for child in children:
            self.assertIsInstance(child, Q)
            lookups = dict(cast("Any", child).children)
            self.assertEqual(set(lookups), {"source__md5", "target__md5"})
            self.assertIsInstance(lookups["source__md5"], MD5)
            self.assertIsInstance(lookups["target__md5"], MD5)
            source = cast("MD5", lookups["source__md5"])
            target = cast("MD5", lookups["target__md5"])
            pairs.add(
                (
                    cast("Any", source.source_expressions[0]).value,
                    cast("Any", target.source_expressions[0]).value,
                )
            )
        return pairs

    def assert_md5_value(self, expression: MD5, value: str) -> None:
        self.assertIsInstance(expression, MD5)
        self.assertEqual(cast("Any", expression.source_expressions[0]).value, value)


class MemoryModelTest(FixtureTestCase):
    def import_memory_with_callbacks(
        self, project_id: int, component_id: int | None = None
    ) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            import_memory(project_id, component_id)

    def handle_unit_translation_change_with_callbacks(self, unit, user) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            handle_unit_translation_change(unit, user)

    def translate_with_callbacks(self, unit, user, target: str, state: int) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            unit.translate(user, target, state)

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

    def test_machine_personal_memory_does_not_fetch_users(self) -> None:
        unit = self.get_unit()
        language_en = Language.objects.get(code="en")
        language_cs = Language.objects.get(code="cs")
        for index in range(3):
            Memory.objects.create(
                source_language=language_en,
                target_language=language_cs,
                source="Hello",
                target=f"Ahoj {index}",
                origin=f"test {index}",
                user=self.user,
                status=Memory.STATUS_ACTIVE,
            )

        machine_translation = WeblateMemory({})

        with CaptureQueriesContext(connection) as queries:
            results = machine_translation.search(unit, "Hello", self.user)

        self.assertEqual(len(results), 3)
        self.assertTrue(all(result["delete_url"] for result in results))
        user_queries = [
            query["sql"] for query in queries if '"weblate_auth_user"' in query["sql"]
        ]
        self.assertEqual(user_queries, [])

    def test_machine_batch(self) -> None:
        add_document()
        unit = self.get_unit()
        machine_translation = WeblateMemory({})
        unit.source = "Hello"
        machine_translation.batch_translate([unit])
        machinery = unit.machinery
        del machinery["origin"]
        self.assertEqual(machinery, {"quality": [100], "translation": ["Ahoj"]})

    def test_machine_plurals(self) -> None:
        unit = self.get_unit("Orangutan has %d banana.\n")

        # Use plural with zero
        translation = unit.translation
        language = translation.language
        plural = translation.plural
        translation.plural = language.plural_set.get_or_create(
            source=Plural.SOURCE_CLDR_ZERO,
            defaults={
                "formula": FORMULA_WITH_ZERO[plural.formula],
                "number": plural.number + 1,
            },
        )[0]
        translation.save()

        add_document("Orangutan has banana.", "Orangutan má banán.")
        machine_translation = WeblateMemory({})
        # Use ridiculously low threshold to get matches on all PostgreSQL versions
        # while testing as this behavior differs.
        machine_translation.batch_translate([unit], threshold=1)
        machinery = unit.machinery
        del machinery["origin"]
        self.assertEqual(
            machinery,
            {
                "quality": [89, 91, 89, 89],
                "translation": [
                    "Orangutan má banán.",
                    "Orangutan má banán.",
                    "Orangutan má banán.",
                    "Orangutan má banán.",
                ],
            },
        )

    def do_import_file_command_test(
        self, filename: str, expected_count: int, **cmd_kwargs
    ) -> None:
        call_command("import_memory", filename, **cmd_kwargs)
        self.assertEqual(
            Memory.objects.filter(status=Memory.STATUS_ACTIVE, from_file=True).count(),
            expected_count,
        )

    def test_import_tmx_command(self) -> None:
        self.do_import_file_command_test(get_test_file("memory.tmx"), 2)
        memory = Memory.objects.filter(
            status=Memory.STATUS_ACTIVE, from_file=True
        ).first()
        self.assertEqual(memory.context, "Context")

    def test_import_tmx2_command(self) -> None:
        self.do_import_file_command_test(get_test_file("memory2.tmx"), 1)

    def test_imported_memory_status(self) -> None:
        unit = self.get_unit()
        unit.context = "Unit Context"
        unit.save()
        self.project.translation_review = True
        self.project.save()
        machine_translation = WeblateMemory({})
        with tempfile.NamedTemporaryFile(suffix=".json") as temp_file:
            temp_file.write(
                json.dumps(
                    [
                        {
                            "source_language": "en",
                            "target_language": "cs",
                            "source": "Hello, world!\n",
                            "target": "Ahoj!",
                            "origin": "Project",
                            "context": "Unit Context",
                            "category": 1,
                        }
                    ]
                ).encode("utf-8")
            )
            temp_file.flush()
            call_command("import_memory", temp_file.name)
        self.assertEqual(Memory.objects.count(), 1)
        suggestion = self.search_suggestion(
            machine_translation, unit, "Hello, world!\n", origin="File"
        )
        # quality of imported memory is not affected by penalty
        self.assertEqual(suggestion["quality"], 100)

        unit.context = "Different context"
        unit.save()
        unit.refresh_from_db()
        suggestion = self.search_suggestion(
            machine_translation, unit, "Hello, world!\n", origin="File"
        )
        self.assertEqual(suggestion["quality"], 95)

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
        self.do_import_file_command_test(get_test_file("memory.json"), 1)

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
        filepath: str,
        source_language: str,
        target_language: str,
        expected_result: int,
    ) -> None:
        """Test memory file upload requiring source and target languages."""
        # check source and target languages are required
        with self.assertRaises(CommandError):
            call_command("import_memory", filepath)
        self.assertEqual(Memory.objects.count(), 0)

        with self.assertRaises(CommandError):
            call_command(
                "import_memory",
                filepath,
                source_language=source_language,
            )
        self.assertEqual(Memory.objects.count(), 0)

        with self.assertRaises(CommandError):
            call_command(
                "import_memory",
                filepath,
                target_language=target_language,
            )
        self.assertEqual(Memory.objects.count(), 0)

        #  check unknown languages raise Error
        with self.assertRaises(CommandError):
            call_command(
                "import_memory",
                filepath,
                source_language=source_language,
                target_language="zzz",
            )
        self.assertEqual(Memory.objects.count(), 0)

        # successful import
        self.do_import_file_command_test(
            filepath,
            expected_result,
            source_language="en",
            target_language="cs",
        )

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

        self.import_file_with_languages_test(
            get_test_file("ids-translated.xliff"), "en", "cs", 2
        )

    def test_import_po(self) -> None:
        """Test the import of an GNU PO file."""
        with tempfile.NamedTemporaryFile(suffix=".po") as temp_file:
            temp_file.write(
                rb"""
msgid ""
msgstr ""
"Project-Id-Version: Weblate Hello World 2012\n"
"Report-Msgid-Bugs-To: <noreply@example.net>\n"
"POT-Creation-Date: 2012-03-14 15:54+0100\n"
"PO-Revision-Date: 2013-08-25 15:23+0200\n"
"Last-Translator: testuser <>\n"
"Language-Team: Czech <http://example.com/projects/test/test/cs/>\n"
"Language: cs\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Plural-Forms: nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;\n"
"X-Generator: Weblate 1.7-dev\n"

#: main.c:11
#, c-format
msgctxt "Greeting"
msgid "Hello, world!\n"
msgstr "Nazdar svete!\n"
"""
            )
            temp_file.flush()
            self.import_file_with_languages_test(temp_file.name, "en", "cs", 1)
        memory = Memory.objects.get()
        self.assertEqual(memory.context, "Greeting")

    def test_import_unsupported_format(self) -> None:
        """Test the import of an unsupported file."""
        with self.assertRaises(CommandError):
            self.import_file_with_languages_test(get_test_file("cs.ts"), "en", "cs", 0)

    def test_import_project(self) -> None:
        self.import_memory_with_callbacks(self.project.id)
        self.assertEqual(Memory.objects.count(), 4)
        self.import_memory_with_callbacks(self.project.id)
        self.assertEqual(Memory.objects.count(), 4)

    def test_user_contribute_personal_tm(self) -> None:
        self.user.profile.contribute_personal_tm = False
        self.user.profile.save()

        unit = self.get_unit()
        self.translate_with_callbacks(unit, self.user, "Nazdar", STATE_TRANSLATED)
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
        with self.captureOnCommitCallbacks(execute=True):
            component.save()

        unit = self.get_unit()
        self.translate_with_callbacks(unit, self.user, "Nazdar", STATE_TRANSLATED)
        # hello, world! unit X 2 (user memory and shared memory)
        self.assertEqual(Memory.objects.count(), 2)

        component.contribute_project_tm = True
        with self.captureOnCommitCallbacks(execute=True):
            component.save()
        # hello, world! unit X 3 (user, project and shared memory)
        # + other units (try weblate string) in the components
        # 2 translations X 2 (project and shared memory) = total 7
        self.assertEqual(Memory.objects.count(), 7)

    def test_component_project_tm_import_scheduled_only_when_reenabled(self) -> None:
        with patch(
            "weblate.trans.models.component.import_memory.delay_on_commit"
        ) as mocked_import:
            component = self._create_component(
                "po", "po/*.po", name="memory", project=self.project
            )

        mocked_import.assert_not_called()

        component.contribute_project_tm = False
        with patch(
            "weblate.trans.models.component.import_memory.delay_on_commit"
        ) as mocked_import:
            component.save()

        mocked_import.assert_not_called()

        component.contribute_project_tm = True
        with patch(
            "weblate.trans.models.component.import_memory.delay_on_commit"
        ) as mocked_import:
            component.save()

        mocked_import.assert_called_once_with(self.project.id, component.pk)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_component_batched_project_tm_update(self) -> None:
        unit = self.get_unit()
        self.translate_with_callbacks(unit, self.user, "Nazdar", STATE_TRANSLATED)
        Memory.objects.all().delete()
        unit.refresh_from_db()
        component = unit.translation.component

        component.start_batched_memory()
        unit.update_translation_memory(needs_user_check=False)
        unit.update_translation_memory(needs_user_check=False)
        self.assertEqual(Memory.objects.count(), 0)

        component.run_batched_memory()
        self.assertEqual(Memory.objects.filter(project=self.project).count(), 1)
        self.assertEqual(Memory.objects.filter(shared=True).count(), 1)
        self.assertEqual(Memory.objects.count(), 2)

        component.start_batched_memory()
        unit.update_translation_memory(needs_user_check=False)
        component.run_batched_memory()
        self.assertEqual(Memory.objects.count(), 2)

    def test_import_unit(self) -> None:
        unit = self.get_unit()
        self.handle_unit_translation_change_with_callbacks(unit, self.user)
        self.assertEqual(Memory.objects.count(), 0)
        self.handle_unit_translation_change_with_callbacks(unit, self.user)
        self.assertEqual(Memory.objects.count(), 0)
        self.translate_with_callbacks(unit, self.user, "Nazdar", STATE_TRANSLATED)
        self.assertEqual(Memory.objects.count(), 3)
        Memory.objects.all().delete()
        self.handle_unit_translation_change_with_callbacks(unit, self.user)
        self.assertEqual(Memory.objects.count(), 3)
        self.handle_unit_translation_change_with_callbacks(unit, self.user)
        self.assertEqual(Memory.objects.count(), 3)

    def test_memory_status_no_review(self) -> None:
        self.test_memory_status_with_review(translation_review=False)

    def test_memory_status_with_review(self, translation_review: bool = True) -> None:
        self.project.translation_review = translation_review
        self.project.save()
        machine_translation = WeblateMemory({})

        unit = self.get_unit()
        self.translate_with_callbacks(unit, self.user, "Hello", STATE_TRANSLATED)

        # check memory status is created with status pending
        expected_status = (
            Memory.STATUS_PENDING if translation_review else Memory.STATUS_ACTIVE
        )
        self.assertEqual(
            1,
            Memory.objects.filter(project=self.project, status=expected_status).count(),
        )
        suggestion = self.search_suggestion(
            machine_translation, unit, "Hello, world!\n"
        )
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
            suggestion = self.search_suggestion(
                machine_translation, unit, "Hello, world!\n"
            )
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
            suggestion = self.search_suggestion(
                machine_translation, unit, "Hello, world!\n"
            )
            self.assertLess(suggestion["quality"], 100)

    def approve_translation(self, unit, target: str, review: str = "30") -> None:
        # allow user to approve translations
        self.project.add_user(self.user, "Administration")
        params = {
            "checksum": unit.checksum,
            "contentsum": hash_to_checksum(unit.content_hash),
            "translationsum": hash_to_checksum(unit.get_target_hash()),
            "target_0": target,
            "review": review,
        }
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(unit.translation.get_translate_url(), params, follow=True)

    def search_suggestion(
        self,
        mt,
        unit,
        source: str,
        user=None,
        text: str | None = None,
        origin: str = "Project",
    ) -> dict:
        results = mt.search(unit, source, user)
        if origin != "File":
            origin = f"{origin}: {self.component.full_slug}"
        results = [r for r in results if origin in r["origin"]]
        if text:
            results = [r for r in results if text in r["text"]]
        return results[0]

    def test_pending_memory_autoclean(self, autoclean_active: bool = False) -> None:
        self.import_memory_with_callbacks(self.project.id)
        imported_memory_ids = [m.pk for m in Memory.objects.all()]
        initial_memory_count = len(imported_memory_ids)
        not_imported_memory_qs = Memory.objects.exclude(id__in=imported_memory_ids)

        # create a translation with review enabled
        self.project.translation_review = True
        self.project.save()
        machine_translation = WeblateMemory({})

        unit = self.get_unit()
        self.translate_with_callbacks(unit, self.user, "Hello 1", STATE_TRANSLATED)

        # check memory status is created with status pending
        self.assertEqual(
            1,
            not_imported_memory_qs.filter(
                project=self.project, context=unit.context, status=Memory.STATUS_PENDING
            ).count(),
        )

        # check that suggestion quality is less than 100% because of penalty
        suggestion = self.search_suggestion(
            machine_translation, unit, "Hello, world!\n"
        )
        self.assertLess(suggestion["quality"], 100)

        # another user submits a translation
        self.translate_with_callbacks(
            unit, self.anotheruser, "Hello 2", STATE_TRANSLATED
        )
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
        suggestion = self.search_suggestion(
            machine_translation, unit, "Hello, world!\n", text="Hello 1"
        )
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

        self.import_memory_with_callbacks(self.project.id)
        excepted_deleted_count = 0

        unit = self.get_unit()

        self.project.translation_review = translation_review
        self.project.save()

        self.translate_with_callbacks(unit, self.user, "Hello 1", STATE_TRANSLATED)
        self.translate_with_callbacks(
            unit, self.anotheruser, "Hello 2", STATE_TRANSLATED
        )

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
        self.translate_with_callbacks(
            unit, self.user, "Hello no context", STATE_TRANSLATED
        )
        self.translate_with_callbacks(
            unit2, self.user, "Hello with context", STATE_TRANSLATED
        )

        if translation_review:
            self.approve_translation(unit, "Hello no context")
            self.approve_translation(unit2, "Hello with context")

        suggestions = machine_translation.search(unit, unit.source, None)
        # ruff: ignore[unnecessary-iterable-allocation-for-first-element]
        with_context = [s for s in suggestions if "Hello with context" in s["text"]][0]
        # ruff: ignore[unnecessary-iterable-allocation-for-first-element]
        no_context = [s for s in suggestions if "Hello no context" in s["text"]][0]
        self.assertLess(with_context["quality"], no_context["quality"])

        # check that memory with different context is not affected by autoclean
        if autoclean_tm:
            self.translate_with_callbacks(
                unit, self.user, "New translation", STATE_TRANSLATED
            )
            self.approve_translation(unit, "New translation")
            suggestions = machine_translation.search(unit, unit.source, None)

            self.assertFalse(
                [s for s in suggestions if "Hello no context" in s["text"]]
            )
            self.assertTrue([s for s in suggestions if "New translation" in s["text"]])
            self.assertTrue(
                [s for s in suggestions if "Hello with context" in s["text"]]
            )

    def test_memory_context_with_review_no_autoclean(self) -> None:
        self.test_memory_context(False, True)

    def test_memory_context_with_review_and_autoclean(self) -> None:
        self.test_memory_context(True, True)

    def test_memory_context_no_review_with_autoclean(self) -> None:
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
            data: dict[str, Any] = {"file": handle}
            if source_language:
                data |= {"source_language": source_language}
            if target_language:
                data |= {"target_language": target_language}

            return self.client.post(
                reverse(f"{prefix}memory-upload", **kwargs),
                data,
                follow=True,
            )

    @override_settings(TRANSLATION_UPLOAD_MAX_SIZE=1)
    def test_upload_too_big(self) -> None:
        handle = BytesIO(b"xx")
        handle.name = "memory.tmx"
        response = self.client.post(
            reverse("memory-upload"),
            {"file": handle},
            follow=True,
        )

        self.assertContains(response, "Uploaded translation file is too big.")

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
            with self.captureOnCommitCallbacks(execute=True):
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
                with self.captureOnCommitCallbacks(execute=True):
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
            Memory.objects.threshold_to_similarity("x", 80), 0.97, delta=0.01
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
            Memory.objects.threshold_to_similarity("x", 75), 0.97, delta=0.01
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

    def test_minimum_similarity_short_strings(self) -> None:
        self.assertEqual(Memory.objects.minimum_similarity("Username", 75), 0.92)
        self.assertEqual(Memory.objects.minimum_similarity("Display name", 75), 0.9)
        self.assertAlmostEqual(
            Memory.objects.minimum_similarity("x" * 50, 75), 0.76, delta=0.01
        )
        self.assertEqual(Memory.objects.minimum_similarity("x", 100), 1.0)


class LookupPolicyTest(SimpleTestCase):
    def test_filter_type_scopes_file_entries_to_global_pool(self) -> None:
        base = MagicMock()
        filtered = MagicMock()
        base.filter.return_value = filtered
        user = MagicMock()
        project = MagicMock()

        with (
            patch.dict(
                "weblate.memory.models.settings.DATABASES",
                {"default": {}, "memory_db": {}},
            ),
            patch.object(MemoryQuerySet, "using", return_value=base),
        ):
            result = Memory.objects.filter_type(
                user=user,
                project=project,
                use_shared=True,
                from_file=True,
            )

        self.assertIs(result, filtered)
        expected = (
            Q(from_file=True, user__isnull=True, project__isnull=True)
            | Q(shared=True)
            | Q(project=project)
            | Q(user=user)
        )
        self.assertEqual(
            base.filter.call_args.args[0].deconstruct(), expected.deconstruct()
        )

    @patch("weblate.memory.models.adjust_similarity_threshold")
    def test_lookup_short_strings_stop_backing_off_early(
        self, adjust_threshold
    ) -> None:
        base = MagicMock()
        base.filter_type.return_value = base
        base.filter.return_value = []

        with patch.object(MemoryQuerySet, "prefetch_project", return_value=base):
            results = Memory.objects.lookup("en", "cs", "Username", None, None, False)

        self.assertEqual(list(results), [])
        base.filter_type.assert_called_once_with(
            user=None,
            project=None,
            use_shared=False,
            from_file=True,
        )
        self.assertEqual(adjust_threshold.call_args_list, [call(0.97), call(0.92)])

    @patch("weblate.memory.models.adjust_similarity_threshold")
    def test_lookup_long_strings_stop_backing_off_for_machinery(
        self, adjust_threshold
    ) -> None:
        base = MagicMock()
        base.filter_type.return_value = base
        base.filter.return_value = []
        text = "x" * 50
        initial = Memory.objects.threshold_to_similarity(text, 80)
        minimum = Memory.objects.minimum_similarity(text, 80)

        with patch.object(MemoryQuerySet, "prefetch_project", return_value=base):
            results = Memory.objects.lookup("en", "cs", text, None, None, False, 80)

        self.assertEqual(list(results), [])
        self.assertEqual(
            adjust_threshold.call_args_list,
            [
                call(initial),
                call(round(initial - 0.05, 3)),
                call(round(initial - 0.1, 3)),
                call(round(initial - 0.15, 3)),
                call(minimum),
            ],
        )

    @patch("weblate.memory.models.adjust_similarity_threshold")
    def test_lookup_exact_threshold_uses_single_exact_probe(
        self, adjust_threshold
    ) -> None:
        base = MagicMock()
        base.filter_type.return_value = base
        base.filter.return_value = []

        with patch.object(MemoryQuerySet, "prefetch_project", return_value=base):
            results = Memory.objects.lookup(
                "en", "cs", "Username", None, None, False, 100
            )

        self.assertEqual(list(results), [])
        base.filter_type.assert_called_once_with(
            user=None,
            project=None,
            use_shared=False,
            from_file=True,
        )
        adjust_threshold.assert_not_called()
        base.filter.assert_called_once_with(
            source="Username",
            source_language="en",
            target_language="cs",
        )
