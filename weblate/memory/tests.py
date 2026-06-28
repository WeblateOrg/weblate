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

from django.apps import apps as django_apps
from django.core.exceptions import FieldDoesNotExist, FieldError
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
from kombu.exceptions import OperationalError
from weblate_schemas import load_schema

from weblate.lang.data import FORMULA_WITH_ZERO
from weblate.lang.models import Language, Plural
from weblate.memory.machine import WeblateMemory
from weblate.memory.models import (
    Memory,
    MemoryImportError,
    MemoryQuerySet,
    MemoryScope,
    load_memory_json_data,
    load_memory_tmx_store,
)
from weblate.memory.tasks import (
    MEMORY_UPDATE_LOOKUP_CHUNK_SIZE,
    cleanup_orphaned_memory,
    compact_memory_scopes,
    get_group_matching_memory,
    handle_unit_translation_change,
    import_memory,
    set_scope_source_project_ids,
    update_memory,
    update_memory_bulk,
)
from weblate.memory.utils import (
    CATEGORY_FILE,
    CATEGORY_PRIVATE_OFFSET,
    CATEGORY_SHARED,
)
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change, Project
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import create_another_user, get_test_file
from weblate.utils.hash import hash_to_checksum
from weblate.utils.state import STATE_TRANSLATED
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from weblate.memory.apps import MemoryConfig
    from weblate.memory.tasks import MemoryGroupEntry


def add_document(source: str = "Hello", target: str = "Ahoj") -> None:
    Memory.objects.create(
        source_language=Language.objects.get(code="en"),
        target_language=Language.objects.get(code="cs"),
        source=source,
        target=target,
        origin="test",
        legacy_from_file=True,
        legacy_shared=False,
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
                "origin__md5",
                "source_language_id",
                "target_language_id",
            },
        )
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
                "add_workspace": False,
                "add_project": True,
                "add_user": False,
                "user_id": None,
                "workspace_id": None,
                "project_id": 1,
                "unit_state": STATE_TRANSLATED,
            },
            Memory.STATUS_ACTIVE,
        )

    def get_matching_memory(self, source: str, target: str) -> MagicMock:
        project_scope = MagicMock(
            scope=MemoryScope.SCOPE_PROJECT,
            project_id=1,
        )
        return MagicMock(
            origin="origin",
            source_language_id=1,
            target_language_id=2,
            source=source,
            target=target,
            status=Memory.STATUS_PENDING,
            legacy_user_id=None,
            legacy_project_id=1,
            legacy_shared=False,
            scopes=MagicMock(all=MagicMock(return_value=[project_scope])),
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
    def project_memory(self, queryset=None):
        if queryset is None:
            queryset = Memory.objects
        return queryset.filter(
            scopes__scope=MemoryScope.SCOPE_PROJECT,
            scopes__project=self.project,
        )

    def test_legacy_memory_owner_fields_are_not_public(self) -> None:
        for field in ("project", "user", "shared", "from_file"):
            with self.assertRaises(FieldDoesNotExist):
                Memory._meta.get_field(field)  # noqa: SLF001

        for lookup in (
            {"project": self.project},
            {"user": self.user},
            {"shared": True},
            {"from_file": True},
        ):
            with self.assertRaises(FieldError):
                Memory.objects.filter(**lookup).exists()

        for obj, attr in ((self.project, "memory_set"), (self.user, "memory_set")):
            with self.assertRaises(AttributeError):
                getattr(obj, attr)

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

    def test_machine_labels_compacted_shared_scope_by_visible_scope(self) -> None:
        unit = self.get_unit()
        source_project = Project.objects.create(
            name="Shared memory source",
            slug="shared-memory-source",
            contribute_shared_tm=True,
        )
        self.project.use_shared_tm = True
        self.project.save(update_fields=["use_shared_tm"])
        memory = Memory.objects.create(
            source_language=Language.objects.get(code="en"),
            target_language=Language.objects.get(code="cs"),
            source=unit.source,
            target="Sdileny kompaktni cil",
            origin="shared-memory-source/component",
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT,
            project=source_project,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_SHARED,
            source_project=source_project,
        )

        suggestions = list(WeblateMemory({}).search(unit, unit.source, None))

        self.assertEqual(suggestions[0]["origin"], f"Shared: {memory.origin}")

    def test_origin_display_labels_compacted_workspace_scope_by_visible_scope(
        self,
    ) -> None:
        workspace = Workspace.objects.create(
            name="Workspace memory source",
            use_workspace_tm=True,
            contribute_workspace_tm=True,
        )
        source_project = Project.objects.create(
            name="Workspace memory source",
            slug="workspace-memory-source",
            workspace=workspace,
            contribute_workspace_tm=True,
        )
        self.project.workspace = workspace
        self.project.use_workspace_tm = True
        self.project.save(update_fields=["workspace", "use_workspace_tm"])
        memory = Memory.objects.create(
            source_language=Language.objects.get(code="en"),
            target_language=Language.objects.get(code="cs"),
            source="Workspace compacted source",
            target="Pracovni kompaktni cil",
            origin="workspace-memory-source/component",
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT,
            project=source_project,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_WORKSPACE,
            workspace=workspace,
            source_project=source_project,
        )
        memory = Memory.objects.prefetch_scopes().get(pk=memory.pk)

        self.assertEqual(
            memory.get_origin_display(project=self.project, user=None),
            f"Workspace: {memory.origin}",
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
                legacy_user=self.user,
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
            MemoryScope.objects.filter(
                scope=MemoryScope.SCOPE_GLOBAL_FILE,
                memory__status=Memory.STATUS_ACTIVE,
            ).count(),
            expected_count,
        )

    def test_import_tmx_command(self) -> None:
        self.do_import_file_command_test(get_test_file("memory.tmx"), 2)
        scope = (
            MemoryScope.objects.filter(
                scope=MemoryScope.SCOPE_GLOBAL_FILE,
                memory__status=Memory.STATUS_ACTIVE,
            )
            .select_related("memory")
            .first()
        )
        assert scope is not None
        self.assertEqual(scope.memory.context, "Context")

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

    def test_dump_command_expands_compacted_project_scopes(self) -> None:
        other_project = Project.objects.create(
            name="Other dump project", slug="other-dump-project"
        )
        memory = Memory.objects.create(
            source_language=Language.objects.get(code="en"),
            target_language=Language.objects.get(code="cs"),
            source="Compacted dump source",
            target="Kompaktni exportovany cil",
            origin="test",
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT,
            project=self.project,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT,
            project=other_project,
        )

        output = StringIO()
        call_command("dump_memory", stdout=output)
        data = json.loads(output.getvalue())
        entries = [entry for entry in data if entry["source"] == memory.source]

        self.assertEqual(len(entries), 2)
        self.assertEqual(
            {entry["category"] for entry in entries},
            {
                CATEGORY_PRIVATE_OFFSET + self.project.pk,
                CATEGORY_PRIVATE_OFFSET + other_project.pk,
            },
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

    def test_component_rename_updates_automatic_memory_origin(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        origin = self.component.full_slug
        project_entry = Memory.objects.create(
            source_language=source_language,
            target_language=target_language,
            source="Renamed project component",
            target="Prejmenovana projektova komponenta",
            origin=origin,
            legacy_project=self.project,
            status=Memory.STATUS_ACTIVE,
        )
        shared_entry = Memory(
            source_language=source_language,
            target_language=target_language,
            source="Renamed component",
            target="Prejmenovana komponenta",
            origin=origin,
            legacy_shared=True,
            status=Memory.STATUS_ACTIVE,
        )
        shared_entry.scope_source_project_id = self.project.id
        shared_entry.save()
        legacy_shared_entry = Memory.objects.create(
            source_language=source_language,
            target_language=target_language,
            source="Legacy renamed component",
            target="Stara prejmenovana komponenta",
            origin=origin,
            legacy_shared=True,
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.filter(memory=legacy_shared_entry).delete()

        self.component.slug = "renamed-memory"
        with patch(
            "weblate.trans.models.component.import_memory.delay_on_commit"
        ) as mocked_import:
            self.component.save()

        new_origin = "/".join(self.component.get_url_path())
        memory_ids = [project_entry.pk, shared_entry.pk]
        self.assertFalse(
            Memory.objects.filter(pk__in=memory_ids, origin=origin).exists()
        )
        project_entry.refresh_from_db()
        shared_entry.refresh_from_db()
        legacy_shared_entry.refresh_from_db()
        self.assertEqual(project_entry.origin, new_origin)
        self.assertEqual(project_entry.legacy_project_id, self.project.id)
        self.assertTrue(
            project_entry.scopes.filter(
                scope=MemoryScope.SCOPE_PROJECT, project=self.project
            ).exists()
        )
        self.assertEqual(shared_entry.origin, new_origin)
        self.assertTrue(
            shared_entry.scopes.filter(
                scope=MemoryScope.SCOPE_SHARED, source_project=self.project
            ).exists()
        )
        self.assertEqual(legacy_shared_entry.origin, origin)
        self.assertFalse(legacy_shared_entry.scopes.exists())
        mocked_import.assert_not_called()

    def test_component_project_move_clears_legacy_project_owner(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        old_project = self.project
        new_project = Project.objects.create(
            name="Moved memory project", slug="moved-memory-project"
        )
        origin = self.component.full_slug
        new_origin = f"{new_project.slug}/{self.component.slug}"
        memory = Memory.objects.create(
            source_language=source_language,
            target_language=target_language,
            source="Moved project memory",
            target="Presunuta projektova pamet",
            origin=origin,
            legacy_project=old_project,
            status=Memory.STATUS_ACTIVE,
        )

        self.component.project = new_project
        self.component.rename_automatic_memory_origin(
            origin,
            new_origin,
            old_project.id,
            old_project.workspace_id,
        )

        memory.refresh_from_db()
        self.assertEqual(memory.origin, new_origin)
        self.assertIsNone(memory.legacy_project_id)
        self.assertFalse(
            memory.scopes.filter(
                scope=MemoryScope.SCOPE_PROJECT,
                project=old_project,
            ).exists()
        )
        self.assertTrue(
            memory.scopes.filter(
                scope=MemoryScope.SCOPE_PROJECT,
                project=new_project,
            ).exists()
        )

        old_project.delete()

        self.assertTrue(Memory.objects.filter(pk=memory.pk).exists())

    def test_component_delete_removes_orphaned_scoped_automatic_memory(self) -> None:
        workspace = Workspace.objects.create(name="Orphaned memory workspace")
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        origin = self.component.full_slug
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "origin": origin,
            "status": Memory.STATUS_ACTIVE,
        }
        shared_entry = Memory.objects.create(
            source="Orphaned shared source",
            target="Osiřelý sdílený cíl",
            **values,
        )
        workspace_entry = Memory.objects.create(
            source="Orphaned workspace source",
            target="Osiřelý pracovní cíl",
            **values,
        )
        mixed_entry = Memory.objects.create(
            source="Orphaned mixed source",
            target="Osiřelý smíšený cíl",
            legacy_user=self.user,
            **values,
        )
        MemoryScope.objects.create(
            memory=shared_entry,
            scope=MemoryScope.SCOPE_SHARED,
            source_project=self.project,
        )
        MemoryScope.objects.create(
            memory=workspace_entry,
            scope=MemoryScope.SCOPE_WORKSPACE,
            workspace=workspace,
            source_project=self.project,
        )
        MemoryScope.objects.create(
            memory=mixed_entry,
            scope=MemoryScope.SCOPE_SHARED,
            source_project=self.project,
        )

        self.component.delete_automatic_memory_scopes(
            origin,
            self.project.id,
            workspace.id,
        )

        self.assertFalse(Memory.objects.filter(pk=shared_entry.pk).exists())
        self.assertFalse(Memory.objects.filter(pk=workspace_entry.pk).exists())
        self.assertTrue(Memory.objects.filter(pk=mixed_entry.pk).exists())
        self.assertFalse(
            mixed_entry.scopes.filter(scope=MemoryScope.SCOPE_SHARED).exists()
        )
        self.assertTrue(
            mixed_entry.scopes.filter(
                scope=MemoryScope.SCOPE_USER,
                user=self.user,
            ).exists()
        )

    def test_project_delete_queues_orphaned_memory_cleanup(self) -> None:
        with patch(
            "weblate.memory.tasks.cleanup_orphaned_memory.delay_on_commit"
        ) as mocked_cleanup:
            self.project.delete()

        mocked_cleanup.assert_called_once_with()

    def test_post_migrate_fails_on_celery_publish_failure(self) -> None:
        add_document()
        memory_config = cast("MemoryConfig", django_apps.get_app_config("memory"))

        with (
            patch(
                "weblate.memory.tasks.backfill_memory_scopes.delay",
                side_effect=OperationalError("broker unavailable"),
            ) as mocked_backfill,
            self.assertRaisesMessage(
                CommandError,
                "Could not schedule translation memory scope migration task",
            ),
        ):
            memory_config.post_migrate(memory_config)

        mocked_backfill.assert_called_once_with()

    def test_project_delete_removes_legacy_shared_scoped_memory(self) -> None:
        memory = Memory.objects.create(
            source_language=Language.objects.get(code="en"),
            target_language=Language.objects.get(code="cs"),
            source="Deleted legacy shared source",
            target="Smazany stary sdileny cil",
            origin=self.component.full_slug,
            legacy_shared=True,
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.filter(memory=memory).delete()
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_SHARED,
            source_project=self.project,
        )

        self.project.delete()

        self.assertFalse(Memory.objects.filter(pk=memory.pk).exists())

    def test_cleanup_orphaned_memory_removes_deleted_project_rows(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "origin": self.component.full_slug,
            "status": Memory.STATUS_ACTIVE,
        }
        project_entry = Memory.objects.create(
            source="Deleted project source",
            target="Smazany projektovy cil",
            **values,
        )
        mixed_entry = Memory.objects.create(
            source="Deleted mixed source",
            target="Smazany smiseny cil",
            **values,
        )
        project_file_entry = Memory.objects.create(
            source="Deleted project file source",
            target="Smazany projektovy souborovy cil",
            origin="uploaded-memory.tmx",
            source_language=source_language,
            target_language=target_language,
            status=Memory.STATUS_ACTIVE,
        )
        legacy_entry = Memory.objects.create(
            source="Deleted legacy source",
            target="Smazany stary cil",
            legacy_user=self.user,
            **values,
        )
        unrelated_scoped = Memory.objects.create(
            source="Other scoped source",
            target="Jiny rozsahovy cil",
            origin="other-project/component",
            source_language=source_language,
            target_language=target_language,
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.create(
            memory=project_entry,
            scope=MemoryScope.SCOPE_PROJECT,
            project=self.project,
        )
        MemoryScope.objects.create(
            memory=mixed_entry,
            scope=MemoryScope.SCOPE_PROJECT,
            project=self.project,
        )
        MemoryScope.objects.create(
            memory=mixed_entry,
            scope=MemoryScope.SCOPE_USER,
            user=self.user,
        )
        MemoryScope.objects.create(
            memory=project_file_entry,
            scope=MemoryScope.SCOPE_PROJECT_FILE,
            project=self.project,
        )
        MemoryScope.objects.create(
            memory=unrelated_scoped,
            scope=MemoryScope.SCOPE_USER,
            user=self.user,
        )

        self.project.delete()
        cleanup_orphaned_memory()

        self.assertFalse(Memory.objects.filter(pk=project_entry.pk).exists())
        self.assertFalse(Memory.objects.filter(pk=project_file_entry.pk).exists())
        self.assertTrue(Memory.objects.filter(pk=mixed_entry.pk).exists())
        self.assertTrue(Memory.objects.filter(pk=legacy_entry.pk).exists())
        self.assertTrue(Memory.objects.filter(pk=unrelated_scoped.pk).exists())
        self.assertFalse(
            mixed_entry.scopes.filter(scope=MemoryScope.SCOPE_PROJECT).exists()
        )
        self.assertTrue(
            mixed_entry.scopes.filter(
                scope=MemoryScope.SCOPE_USER,
                user=self.user,
            ).exists()
        )

    def test_workspace_delete_scope_removes_compacted_workspace_memory(self) -> None:
        workspace = Workspace.objects.create(name="Memory cleanup workspace")
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "origin": self.component.full_slug,
            "status": Memory.STATUS_ACTIVE,
        }
        workspace_entry = Memory.objects.create(
            source="Workspace cleanup source",
            target="Pracovni uklizeny cil",
            **values,
        )
        mixed_entry = Memory.objects.create(
            source="Mixed workspace cleanup source",
            target="Smiseny pracovni uklizeny cil",
            **values,
        )
        MemoryScope.objects.create(
            memory=workspace_entry,
            scope=MemoryScope.SCOPE_WORKSPACE,
            workspace=workspace,
            source_project=self.project,
        )
        MemoryScope.objects.create(
            memory=mixed_entry,
            scope=MemoryScope.SCOPE_WORKSPACE,
            workspace=workspace,
            source_project=self.project,
        )
        MemoryScope.objects.create(
            memory=mixed_entry,
            scope=MemoryScope.SCOPE_USER,
            user=self.user,
        )

        workspace.delete_workspace_memory_scope()

        self.assertFalse(Memory.objects.filter(pk=workspace_entry.pk).exists())
        self.assertTrue(Memory.objects.filter(pk=mixed_entry.pk).exists())
        self.assertFalse(
            mixed_entry.scopes.filter(scope=MemoryScope.SCOPE_WORKSPACE).exists()
        )
        self.assertTrue(
            mixed_entry.scopes.filter(scope=MemoryScope.SCOPE_USER).exists()
        )

    def test_unscoped_legacy_shared_entry_does_not_block_resharing(self) -> None:
        self.project.contribute_shared_tm = False
        self.project.save(update_fields=["contribute_shared_tm"])
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        source = "Legacy shared source"
        origin = self.component.full_slug
        legacy = Memory.objects.create(
            source_language=source_language,
            target_language=target_language,
            source=source,
            target="Starý sdílený cíl",
            origin=origin,
            legacy_shared=True,
            status=Memory.STATUS_ACTIVE,
        )
        self.assertTrue(legacy.scopes.filter(scope=MemoryScope.SCOPE_SHARED).exists())
        MemoryScope.objects.filter(memory=legacy).delete()

        self.project.contribute_shared_tm = True
        self.project.save(update_fields=["contribute_shared_tm"])
        update_memory(
            source_language_id=source_language.id,
            target_language_id=target_language.id,
            source=source,
            context="",
            target="Starý sdílený cíl",
            origin=origin,
            add_shared=True,
            add_workspace=False,
            add_project=False,
            add_user=False,
            user_id=None,
            workspace_id=None,
            project_id=self.project.id,
            unit_state=STATE_TRANSLATED,
        )

        self.assertTrue(
            MemoryScope.objects.filter(
                memory__source=source,
                scope=MemoryScope.SCOPE_SHARED,
            ).exists()
        )

    def test_scope_source_project_uses_project_rename_history(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        old_slug = "old-project-slug"
        Change.objects.create(
            project=self.project,
            action=ActionEvents.RENAME_PROJECT,
            old=old_slug,
        )
        Change.objects.generate_project_rename_lookup()
        memory = Memory.objects.create(
            source_language=source_language,
            target_language=target_language,
            source="Renamed legacy shared source",
            target="Prejmenovany stary sdileny cil",
            origin=f"{old_slug}/component",
            legacy_shared=True,
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.filter(memory=memory).delete()

        set_scope_source_project_ids([memory])
        MemoryScope.objects.create_for_memory(memory)

        self.assertTrue(
            memory.scopes.filter(
                scope=MemoryScope.SCOPE_SHARED,
                source_project=self.project,
            ).exists()
        )
        self.assertTrue(
            Memory.objects.filter_type(
                project=self.project,
                use_shared=True,
            )
            .filter(pk=memory.pk)
            .exists()
        )

    def test_update_entry_reuses_compacted_import_scope(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        source = "Compacted imported source"
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "source": source,
            "target": "Kompaktni importovany cil",
            "origin": "compacted-import.tmx",
            "context": "",
            "status": Memory.STATUS_ACTIVE,
        }
        memory = Memory.objects.create(**values)
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT_FILE,
            project=self.project,
        )

        Memory.objects.update_entry(
            user=None,
            project=self.project,
            from_file=True,
            shared=False,
            **values,
        )

        self.assertEqual(Memory.objects.filter(source=source).count(), 1)

        MemoryScope.objects.filter(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT_FILE,
            project=self.project,
        ).delete()
        MemoryScope.objects.create(memory=memory, scope=MemoryScope.SCOPE_GLOBAL_FILE)

        Memory.objects.update_entry(
            user=None,
            project=self.project,
            from_file=True,
            shared=False,
            **values,
        )

        memory.refresh_from_db()
        self.assertEqual(Memory.objects.filter(source=source).count(), 1)
        self.assertTrue(
            memory.scopes.filter(
                scope=MemoryScope.SCOPE_PROJECT_FILE,
                project=self.project,
            ).exists()
        )
        self.assertIsNone(memory.legacy_project_id)
        self.assertFalse(memory.legacy_from_file)

    def test_update_entry_ignores_unbackfilled_legacy_scope(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        target_project = Project.objects.create(
            name="Memory import target", slug="memory-import-target"
        )
        source = "Unbackfilled imported source"
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "source": source,
            "target": "Nezpetne doplneny importovany cil",
            "origin": "legacy-import.tmx",
            "context": "",
            "status": Memory.STATUS_ACTIVE,
        }
        memory = Memory.objects.create(
            legacy_project=self.project,
            legacy_from_file=True,
            **values,
        )
        MemoryScope.objects.filter(memory=memory).delete()

        Memory.objects.update_entry(
            user=None,
            project=target_project,
            from_file=True,
            shared=False,
            **values,
        )

        memory.refresh_from_db()
        self.assertEqual(Memory.objects.filter(source=source).count(), 2)
        self.assertFalse(memory.scopes.exists())
        scoped_memory = Memory.objects.exclude(pk=memory.pk).get(source=source)
        self.assertTrue(
            scoped_memory.scopes.filter(
                scope=MemoryScope.SCOPE_PROJECT_FILE,
                project=target_project,
            ).exists()
        )
        self.assertIsNone(scoped_memory.legacy_project_id)
        self.assertFalse(scoped_memory.legacy_from_file)

    def test_update_entry_normalizes_reused_legacy_owned_memory(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        legacy_project = Project.objects.create(
            name="Legacy import owner", slug="legacy-import-owner"
        )
        target_project = Project.objects.create(
            name="Memory import target", slug="memory-import-target"
        )
        source = "Reused legacy imported source"
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "source": source,
            "target": "Znovu pouzity importovany cil",
            "origin": "reused-legacy-import.tmx",
            "context": "",
            "status": Memory.STATUS_ACTIVE,
        }
        memory = Memory.objects.create(
            legacy_project=legacy_project,
            legacy_from_file=True,
            **values,
        )

        Memory.objects.update_entry(
            user=None,
            project=target_project,
            from_file=True,
            shared=False,
            **values,
        )

        memory.refresh_from_db()
        self.assertIsNone(memory.legacy_project_id)
        self.assertIsNone(memory.legacy_user_id)
        self.assertFalse(memory.legacy_shared)
        self.assertFalse(memory.legacy_from_file)
        self.assertEqual(Memory.objects.filter(source=source).count(), 1)
        self.assertTrue(
            memory.scopes.filter(
                scope=MemoryScope.SCOPE_PROJECT_FILE,
                project=legacy_project,
            ).exists()
        )
        self.assertTrue(
            memory.scopes.filter(
                scope=MemoryScope.SCOPE_PROJECT_FILE,
                project=target_project,
            ).exists()
        )

        legacy_project.delete()

        self.assertTrue(Memory.objects.filter(pk=memory.pk).exists())
        self.assertTrue(
            memory.scopes.filter(
                scope=MemoryScope.SCOPE_PROJECT_FILE,
                project=target_project,
            ).exists()
        )

    def test_autoclean_preserves_imported_scope_on_compacted_memory(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        source = "Autoclean compacted source"
        origin = self.component.full_slug
        self.project.autoclean_tm = True
        self.project.save(update_fields=["autoclean_tm"])
        memory = Memory.objects.create(
            source_language=source_language,
            target_language=target_language,
            source=source,
            target="Stary automaticky cil",
            origin=origin,
            legacy_project=self.project,
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_GLOBAL_FILE,
        )

        update_memory(
            source_language_id=source_language.id,
            target_language_id=target_language.id,
            source=source,
            context="",
            target="Novy automaticky cil",
            origin=origin,
            add_shared=False,
            add_workspace=False,
            add_project=True,
            add_user=False,
            user_id=None,
            workspace_id=None,
            project_id=self.project.id,
            unit_state=STATE_TRANSLATED,
        )

        self.assertTrue(Memory.objects.filter(pk=memory.pk).exists())
        self.assertTrue(
            memory.scopes.filter(scope=MemoryScope.SCOPE_GLOBAL_FILE).exists()
        )
        self.assertFalse(
            memory.scopes.filter(
                scope=MemoryScope.SCOPE_PROJECT,
                project=self.project,
            ).exists()
        )
        self.assertTrue(
            Memory.objects.filter(
                source=source,
                target="Novy automaticky cil",
                scopes__scope=MemoryScope.SCOPE_PROJECT,
                scopes__project=self.project,
            ).exists()
        )

    def test_autoclean_preserves_unbackfilled_legacy_file_memory(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        source = "Autoclean legacy file source"
        origin = self.component.full_slug
        self.project.autoclean_tm = True
        self.project.save(update_fields=["autoclean_tm"])
        legacy_file = Memory.objects.create(
            source_language=source_language,
            target_language=target_language,
            source=source,
            target="Stary souborovy cil",
            origin=origin,
            legacy_from_file=True,
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.filter(memory=legacy_file).delete()

        update_memory(
            source_language_id=source_language.id,
            target_language_id=target_language.id,
            source=source,
            context="",
            target="Novy automaticky cil",
            origin=origin,
            add_shared=False,
            add_workspace=False,
            add_project=True,
            add_user=False,
            user_id=None,
            workspace_id=None,
            project_id=self.project.id,
            unit_state=STATE_TRANSLATED,
        )

        self.assertTrue(Memory.objects.filter(pk=legacy_file.pk).exists())
        legacy_file.refresh_from_db()
        self.assertTrue(legacy_file.legacy_from_file)
        self.assertFalse(legacy_file.scopes.exists())
        self.assertTrue(
            Memory.objects.filter(
                source=source,
                target="Novy automaticky cil",
                scopes__scope=MemoryScope.SCOPE_PROJECT,
                scopes__project=self.project,
            ).exists()
        )

    def test_autoclean_removes_unbackfilled_legacy_automatic_memory(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        source = "Autoclean legacy automatic source"
        origin = self.component.full_slug
        self.project.autoclean_tm = True
        self.project.save(update_fields=["autoclean_tm"])
        legacy_automatic = Memory.objects.create(
            source_language=source_language,
            target_language=target_language,
            source=source,
            target="Stary automaticky cil",
            origin=origin,
            legacy_project=self.project,
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.filter(memory=legacy_automatic).delete()

        update_memory(
            source_language_id=source_language.id,
            target_language_id=target_language.id,
            source=source,
            context="",
            target="Novy automaticky cil",
            origin=origin,
            add_shared=False,
            add_workspace=False,
            add_project=True,
            add_user=False,
            user_id=None,
            workspace_id=None,
            project_id=self.project.id,
            unit_state=STATE_TRANSLATED,
        )

        self.assertFalse(Memory.objects.filter(pk=legacy_automatic.pk).exists())
        self.assertTrue(
            Memory.objects.filter(
                source=source,
                target="Novy automaticky cil",
                scopes__scope=MemoryScope.SCOPE_PROJECT,
                scopes__project=self.project,
            ).exists()
        )

    def test_status_update_splits_file_scopes_from_automatic_memory(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        source = "Mixed file automatic source"
        target = "Smiseny souborovy automaticky cil"
        origin = self.component.full_slug
        self.project.translation_review = True
        self.project.save(update_fields=["translation_review"])
        memory = Memory.objects.create(
            source_language=source_language,
            target_language=target_language,
            source=source,
            target=target,
            origin=origin,
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_GLOBAL_FILE,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT,
            project=self.project,
        )

        update_memory(
            source_language_id=source_language.id,
            target_language_id=target_language.id,
            source=source,
            context="",
            target=target,
            origin=origin,
            add_shared=False,
            add_workspace=False,
            add_project=True,
            add_user=False,
            user_id=None,
            workspace_id=None,
            project_id=self.project.id,
            unit_state=STATE_TRANSLATED,
        )

        memory.refresh_from_db()
        self.assertEqual(memory.status, Memory.STATUS_ACTIVE)
        self.assertTrue(
            memory.scopes.filter(scope=MemoryScope.SCOPE_GLOBAL_FILE).exists()
        )
        self.assertFalse(memory.scopes.filter(scope=MemoryScope.SCOPE_PROJECT).exists())
        automatic_memory = Memory.objects.exclude(pk=memory.pk).get(source=source)
        self.assertEqual(automatic_memory.status, Memory.STATUS_PENDING)
        self.assertTrue(
            automatic_memory.scopes.filter(
                scope=MemoryScope.SCOPE_PROJECT,
                project=self.project,
            ).exists()
        )
        self.assertFalse(
            automatic_memory.scopes.filter(scope=MemoryScope.SCOPE_GLOBAL_FILE).exists()
        )

    def test_bulk_status_update_splits_file_scopes_from_automatic_memory(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        source = "Bulk mixed file automatic source"
        target = "Davkovy smiseny cil"
        origin = self.component.full_slug
        self.project.translation_review = True
        self.project.save(update_fields=["translation_review"])
        memory = Memory.objects.create(
            source_language=source_language,
            target_language=target_language,
            source=source,
            target=target,
            origin=origin,
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_GLOBAL_FILE,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT,
            project=self.project,
        )

        update_memory_bulk(
            [
                {
                    "source_language_id": source_language.id,
                    "target_language_id": target_language.id,
                    "source": source,
                    "context": "",
                    "target": target,
                    "origin": origin,
                    "add_shared": False,
                    "add_workspace": False,
                    "add_project": True,
                    "add_user": False,
                    "user_id": None,
                    "workspace_id": None,
                    "project_id": self.project.id,
                    "unit_state": STATE_TRANSLATED,
                }
            ]
        )

        memory.refresh_from_db()
        self.assertEqual(memory.status, Memory.STATUS_ACTIVE)
        self.assertTrue(
            memory.scopes.filter(scope=MemoryScope.SCOPE_GLOBAL_FILE).exists()
        )
        self.assertFalse(memory.scopes.filter(scope=MemoryScope.SCOPE_PROJECT).exists())
        automatic_memory = Memory.objects.exclude(pk=memory.pk).get(source=source)
        self.assertEqual(automatic_memory.status, Memory.STATUS_PENDING)
        self.assertTrue(
            automatic_memory.scopes.filter(
                scope=MemoryScope.SCOPE_PROJECT,
                project=self.project,
            ).exists()
        )

    def test_compact_backfills_scopes_before_merging_duplicates(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "source": "Compacted source",
            "target": "Kompaktni cil",
            "origin": self.component.full_slug,
            "status": Memory.STATUS_ACTIVE,
        }
        project_entry = Memory.objects.create(legacy_project=self.project, **values)
        shared_entry = Memory.objects.create(legacy_shared=True, **values)
        MemoryScope.objects.filter(memory__in=(project_entry, shared_entry)).delete()

        compact_memory_scopes()

        memory = Memory.objects.get(source="Compacted source")
        self.assertEqual(
            set(memory.scopes.values_list("scope", flat=True)),
            {MemoryScope.SCOPE_PROJECT, MemoryScope.SCOPE_SHARED},
        )

    def test_compact_preserves_shared_source_projects(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        other_project = Project.objects.create(
            name="Other shared source", slug="other-shared-source"
        )
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "source": "Compacted shared source",
            "target": "Kompaktni sdileny cil",
            "origin": self.component.full_slug,
            "status": Memory.STATUS_ACTIVE,
        }
        first_entry = Memory.objects.create(**values)
        second_entry = Memory.objects.create(**values)
        MemoryScope.objects.create(
            memory=first_entry,
            scope=MemoryScope.SCOPE_SHARED,
            source_project=self.project,
        )
        MemoryScope.objects.create(
            memory=second_entry,
            scope=MemoryScope.SCOPE_SHARED,
            source_project=other_project,
        )

        compact_memory_scopes()

        memory = Memory.objects.get(source="Compacted shared source")
        self.assertEqual(
            set(
                memory.scopes.filter(scope=MemoryScope.SCOPE_SHARED).values_list(
                    "source_project_id", flat=True
                )
            ),
            {self.project.id, other_project.id},
        )

    def test_compact_preserves_workspace_source_projects(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        workspace = Workspace.objects.create(name="Compacted workspace source")
        other_project = Project.objects.create(
            name="Other workspace source",
            slug="other-workspace-source",
            workspace=workspace,
        )
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "source": "Compacted workspace source",
            "target": "Kompaktni pracoviste cil",
            "origin": self.component.full_slug,
            "status": Memory.STATUS_ACTIVE,
        }
        first_entry = Memory.objects.create(**values)
        second_entry = Memory.objects.create(**values)
        MemoryScope.objects.create(
            memory=first_entry,
            scope=MemoryScope.SCOPE_WORKSPACE,
            workspace=workspace,
            source_project=self.project,
        )
        MemoryScope.objects.create(
            memory=second_entry,
            scope=MemoryScope.SCOPE_WORKSPACE,
            workspace=workspace,
            source_project=other_project,
        )

        compact_memory_scopes()

        memory = Memory.objects.get(source="Compacted workspace source")
        self.assertEqual(
            set(
                memory.scopes.filter(scope=MemoryScope.SCOPE_WORKSPACE).values_list(
                    "workspace_id", "source_project_id"
                )
            ),
            {
                (workspace.id, self.project.id),
                (workspace.id, other_project.id),
            },
        )

    def test_compact_normalizes_multi_scope_survivor_owner_fields(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "source": "Compacted personal source",
            "target": "Kompaktni osobni cil",
            "origin": self.component.full_slug,
            "status": Memory.STATUS_ACTIVE,
        }
        project_entry = Memory.objects.create(legacy_project=self.project, **values)
        user_entry = Memory.objects.create(legacy_user=self.user, **values)

        compact_memory_scopes()

        memory = Memory.objects.get(source="Compacted personal source")
        self.assertEqual(memory.pk, project_entry.pk)
        self.assertFalse(Memory.objects.filter(pk=user_entry.pk).exists())
        self.assertIsNone(memory.legacy_project_id)
        self.assertIsNone(memory.legacy_user_id)
        self.assertFalse(memory.legacy_shared)
        self.assertEqual(
            set(memory.scopes.values_list("scope", flat=True)),
            {MemoryScope.SCOPE_PROJECT, MemoryScope.SCOPE_USER},
        )

        self.project.delete()

        self.assertTrue(Memory.objects.filter(pk=memory.pk).exists())
        self.assertTrue(
            MemoryScope.objects.filter(
                memory=memory, scope=MemoryScope.SCOPE_USER, user=self.user
            ).exists()
        )

    def test_compact_clears_file_flag_on_multi_scope_survivor(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "source": "Compacted uploaded source",
            "target": "Kompaktni nahrany cil",
            "origin": "compacted-upload.tmx",
            "status": Memory.STATUS_ACTIVE,
            "legacy_from_file": True,
        }
        project_entry = Memory.objects.create(legacy_project=self.project, **values)
        user_entry = Memory.objects.create(legacy_user=self.user, **values)

        compact_memory_scopes()

        memory = Memory.objects.get(source="Compacted uploaded source")
        self.assertEqual(memory.pk, project_entry.pk)
        self.assertFalse(Memory.objects.filter(pk=user_entry.pk).exists())
        self.assertIsNone(memory.legacy_project_id)
        self.assertIsNone(memory.legacy_user_id)
        self.assertFalse(memory.legacy_shared)
        self.assertFalse(memory.legacy_from_file)
        self.assertEqual(
            set(memory.scopes.values_list("scope", flat=True)),
            {MemoryScope.SCOPE_PROJECT_FILE, MemoryScope.SCOPE_USER_FILE},
        )

        memory.save()

        self.assertFalse(
            memory.scopes.filter(scope=MemoryScope.SCOPE_GLOBAL_FILE).exists()
        )

    def test_delete_scope_keeps_memory_ids_database_side(self) -> None:
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "origin": "delete-scope-db-side",
            "status": Memory.STATUS_ACTIVE,
        }
        project_only = Memory.objects.create(
            source="Delete project-only scope",
            target="Smazat pouze projektovy rozsah",
            legacy_project=self.project,
            **values,
        )
        project_user = Memory.objects.create(
            source="Delete project scope with personal fallback",
            target="Smazat projektovy rozsah s osobnim rozsahem",
            legacy_project=self.project,
            **values,
        )
        legacy_unscoped = Memory.objects.create(
            source="Delete legacy unscoped scope",
            target="Smazat stary nerozsahovany zaznam",
            legacy_project=self.project,
            **values,
        )
        MemoryScope.objects.create(
            memory=project_user, scope=MemoryScope.SCOPE_USER, user=self.user
        )
        MemoryScope.objects.filter(memory=legacy_unscoped).delete()

        with patch.object(
            MemoryQuerySet,
            "values_list",
            side_effect=AssertionError("delete_scope must keep ids in SQL"),
        ):
            Memory.objects.filter(origin="delete-scope-db-side").delete_scope(
                Q(scope=MemoryScope.SCOPE_PROJECT, project=self.project)
            )

        self.assertFalse(Memory.objects.filter(pk=project_only.pk).exists())
        self.assertFalse(Memory.objects.filter(pk=legacy_unscoped.pk).exists())
        self.assertTrue(Memory.objects.filter(pk=project_user.pk).exists())
        self.assertFalse(
            project_user.scopes.filter(
                scope=MemoryScope.SCOPE_PROJECT, project=self.project
            ).exists()
        )
        self.assertTrue(
            project_user.scopes.filter(
                scope=MemoryScope.SCOPE_USER, user=self.user
            ).exists()
        )

    def test_filter_type_skips_unbackfilled_legacy_entries(self) -> None:
        workspace = Workspace.objects.create(
            name="Legacy skipped workspace",
            use_workspace_tm=True,
            contribute_workspace_tm=True,
        )
        self.project.workspace = workspace
        self.project.use_workspace_tm = True
        self.project.contribute_workspace_tm = True
        self.project.save(
            update_fields=[
                "workspace",
                "use_workspace_tm",
                "contribute_workspace_tm",
            ]
        )
        other_user = create_another_user("-memory-legacy")
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        values = {
            "source_language": source_language,
            "target_language": target_language,
            "origin": self.component.full_slug,
            "status": Memory.STATUS_ACTIVE,
        }
        workspace_entry = Memory.objects.create(
            source="Legacy workspace source",
            target="Stary pracovni cil",
            **values,
        )
        personal_entry = Memory.objects.create(
            source="Legacy personal source",
            target="Stary osobni cil",
            legacy_user=other_user,
            **values,
        )
        file_entry = Memory.objects.create(
            source="Legacy file source",
            target="Stary souborovy cil",
            legacy_from_file=True,
            **values,
        )
        MemoryScope.objects.filter(
            memory__in=(workspace_entry, personal_entry, file_entry)
        ).delete()

        queryset = Memory.objects.filter_type(
            user=self.user,
            project=self.project,
            use_workspace=True,
        )
        self.assertNotIn("legacy_", str(queryset.values("id").query).lower())
        matches = set(queryset.values_list("id", flat=True))

        self.assertNotIn(workspace_entry.id, matches)
        self.assertNotIn(personal_entry.id, matches)
        self.assertNotIn(file_entry.id, matches)

        lookup_queryset = Memory.objects.lookup(
            source_language,
            target_language,
            "Legacy workspace source",
            self.user,
            self.project,
            True,
            threshold=100,
        )
        self.assertNotIn("legacy_", str(lookup_queryset.values("id").query).lower())

        self.project.add_user(self.user, "Administration")
        visible_queryset = Memory.objects.visible_to_user(self.user, alias="default")
        self.assertNotIn("legacy_", str(visible_queryset.values("id").query).lower())
        visible = set(
            visible_queryset.values_list(
                "id",
                flat=True,
            )
        )

        self.assertNotIn(workspace_entry.id, visible)
        self.assertNotIn(personal_entry.id, visible)

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
        self.assertEqual(
            MemoryScope.objects.filter(
                scope=MemoryScope.SCOPE_PROJECT, project=self.project
            ).count(),
            1,
        )
        self.assertEqual(
            MemoryScope.objects.filter(scope=MemoryScope.SCOPE_SHARED).count(),
            1,
        )
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
            self.project_memory().filter(status=expected_status).count(),
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
                self.project_memory().filter(status=Memory.STATUS_ACTIVE).count(),
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
                self.project_memory().filter(status=Memory.STATUS_PENDING).count(),
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
            self.project_memory(not_imported_memory_qs)
            .filter(context=unit.context, status=Memory.STATUS_PENDING)
            .count(),
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
            self.project_memory(not_imported_memory_qs)
            .filter(context=unit.context, status=Memory.STATUS_PENDING)
            .count(),
        )
        for suggestion in machine_translation.search(unit, "Hello, world!\n", None):
            self.assertLess(suggestion["quality"], 100)

        # approve one translation, check that only 1 memory left with status active
        self.approve_translation(unit, "Hello 1")

        self.assertEqual(
            1,
            self.project_memory(not_imported_memory_qs)
            .filter(context=unit.context, status=Memory.STATUS_ACTIVE)
            .count(),
        )
        suggestion = self.search_suggestion(
            machine_translation, unit, "Hello, world!\n", text="Hello 1"
        )
        self.assertEqual(suggestion["quality"], 100)

        if not autoclean_active:
            # check that the other pending memory has not been deleted
            self.assertEqual(
                1,
                self.project_memory(not_imported_memory_qs)
                .filter(context=unit.context, status=Memory.STATUS_PENDING)
                .count(),
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

    def test_rebuild_removes_compacted_automatic_scopes(self) -> None:
        self.project.add_user(self.user, "Administration")
        workspace = Workspace.objects.create(name="Memory rebuild workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        memory = Memory.objects.create(
            source_language=Language.objects.get(code="en"),
            target_language=Language.objects.get(code="cs"),
            source="Rebuild stale scope",
            target="Prestaveny stary rozsah",
            origin=self.component.full_slug,
            legacy_project=self.project,
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_SHARED,
            source_project=self.project,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_WORKSPACE,
            workspace=workspace,
            source_project=self.project,
        )

        with patch("weblate.memory.views.import_memory.delay") as mocked_import:
            response = self.client.post(
                reverse("memory-rebuild", kwargs=self.kw_project),
                {"confirm": "1", "origin": self.component.full_slug},
                follow=True,
            )

        self.assertContains(response, "Entries were deleted and the translation memory")
        self.assertFalse(Memory.objects.filter(pk=memory.pk).exists())
        mocked_import.assert_called_once_with(
            project_id=self.project.id, component_id=self.component.id
        )

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

    def test_shared_memory_download_uses_shared_category(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        source_language = Language.objects.get(code="en")
        target_language = Language.objects.get(code="cs")
        memory = Memory.objects.create(
            source_language=source_language,
            target_language=target_language,
            source="Shared download source",
            target="Sdileny stazeny cil",
            origin=self.component.full_slug,
            legacy_project=self.project,
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_SHARED,
            source_project=self.project,
        )

        response = self.client.get(
            reverse("manage-memory-download"),
            {"format": "json", "kind": "shared"},
        )

        self.assertEqual(response.json()[0]["category"], CATEGORY_SHARED)

    def test_global_memory_download_all_expands_compacted_scopes(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        other_project = Project.objects.create(
            name="Other download project", slug="other-download-project"
        )
        memory = Memory.objects.create(
            source_language=Language.objects.get(code="en"),
            target_language=Language.objects.get(code="cs"),
            source="Global all download source",
            target="Globalni stazeny cil",
            origin=self.component.full_slug,
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT,
            project=self.project,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT,
            project=other_project,
        )

        response = self.client.get(
            reverse("manage-memory-download"),
            {"format": "json", "kind": "all"},
        )
        entries = [
            entry for entry in response.json() if entry["source"] == memory.source
        ]

        self.assertEqual(len(entries), 2)
        self.assertEqual(
            {entry["category"] for entry in entries},
            {
                CATEGORY_PRIVATE_OFFSET + self.project.pk,
                CATEGORY_PRIVATE_OFFSET + other_project.pk,
            },
        )

    def test_project_memory_download_uses_project_category(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        other_project = Project.objects.create(
            name="Other project download category",
            slug="other-project-download-category",
        )
        memory = Memory.objects.create(
            source_language=Language.objects.get(code="en"),
            target_language=Language.objects.get(code="cs"),
            source="Project download source",
            target="Projektovy stazeny cil",
            origin=self.component.full_slug,
            status=Memory.STATUS_ACTIVE,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT,
            project=other_project,
        )
        MemoryScope.objects.create(
            memory=memory,
            scope=MemoryScope.SCOPE_PROJECT,
            project=self.project,
        )

        response = self.client.get(
            reverse("memory-download", kwargs=self.kw_project),
            {"format": "json"},
        )
        entries = [
            entry for entry in response.json() if entry["source"] == memory.source
        ]

        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0]["category"], CATEGORY_PRIVATE_OFFSET + self.project.pk
        )

    def test_memory_download_rejects_invalid_language_filter(self) -> None:
        self.user.is_superuser = True
        self.user.save()

        response = self.client.get(
            reverse("manage-memory-download"),
            {"format": "json", "source_language": "invalid"},
        )

        self.assertEqual(response.status_code, 404)

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
        filtered = MagicMock()
        user = MagicMock()
        project = MagicMock()

        with (
            patch.dict("weblate.memory.models.settings.DATABASES", {"default": {}}),
            patch.object(
                MemoryQuerySet, "filter_scope", return_value=filtered
            ) as filter_scope,
        ):
            result = Memory.objects.filter_type(
                user=user,
                project=project,
                use_shared=True,
                from_file=True,
            )

        self.assertIs(result, filtered)
        (scope_query,) = filter_scope.call_args.args
        expected_scope = (
            Q(pk__isnull=True)
            | Q(scope=MemoryScope.SCOPE_GLOBAL_FILE)
            | Q(
                scope=MemoryScope.SCOPE_SHARED,
                source_project__contribute_shared_tm=True,
            )
            | Q(scope=MemoryScope.SCOPE_PROJECT, project=project)
            | Q(scope=MemoryScope.SCOPE_PROJECT_FILE, project=project)
            | Q(scope=MemoryScope.SCOPE_USER, user=user)
            | Q(scope=MemoryScope.SCOPE_USER_FILE, user=user)
        )
        self.assertEqual(scope_query.deconstruct(), expected_scope.deconstruct())

    def test_lookup_prefetch_scopes_uses_memory_database_alias(self) -> None:
        with patch.dict(
            "weblate.memory.models.settings.DATABASES",
            {"default": {}, "memory_db": {}},
        ):
            queryset = Memory.objects.filter_type(from_file=True)

        with patch.object(
            MemoryScope.objects, "using", wraps=MemoryScope.objects.using
        ) as using_mock:
            queryset.prefetch_scopes()

        self.assertEqual(queryset.db, "memory_db")
        using_mock.assert_called_once_with("memory_db")

    @patch("weblate.memory.models.adjust_similarity_threshold")
    def test_lookup_short_strings_stop_backing_off_early(
        self, adjust_threshold
    ) -> None:
        base = MagicMock()
        base.prefetch_scopes.return_value = base
        base.filter.return_value = []

        with patch.object(
            MemoryQuerySet, "filter_type", return_value=base
        ) as filter_type:
            results = Memory.objects.lookup("en", "cs", "Username", None, None, False)

        self.assertEqual(list(results), [])
        filter_type.assert_called_once_with(
            user=None,
            project=None,
            use_shared=False,
            from_file=True,
            use_workspace=True,
        )
        base.prefetch_scopes.assert_called_once_with()
        self.assertEqual(adjust_threshold.call_args_list, [call(0.97), call(0.92)])

    @patch("weblate.memory.models.adjust_similarity_threshold")
    def test_lookup_long_strings_stop_backing_off_for_machinery(
        self, adjust_threshold
    ) -> None:
        base = MagicMock()
        base.prefetch_scopes.return_value = base
        base.filter.return_value = []
        text = "x" * 50
        initial = Memory.objects.threshold_to_similarity(text, 80)
        minimum = Memory.objects.minimum_similarity(text, 80)

        with patch.object(MemoryQuerySet, "filter_type", return_value=base):
            results = Memory.objects.lookup("en", "cs", text, None, None, False, 80)

        self.assertEqual(list(results), [])
        base.prefetch_scopes.assert_called_once_with()
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
        base.prefetch_scopes.return_value = base
        base.filter.return_value = []

        with patch.object(
            MemoryQuerySet, "filter_type", return_value=base
        ) as filter_type:
            results = Memory.objects.lookup(
                "en", "cs", "Username", None, None, False, 100
            )

        self.assertEqual(list(results), [])
        filter_type.assert_called_once_with(
            user=None,
            project=None,
            use_shared=False,
            from_file=True,
            use_workspace=True,
        )
        base.prefetch_scopes.assert_called_once_with()
        adjust_threshold.assert_not_called()
        base.filter.assert_called_once_with(
            source="Username",
            source_language="en",
            target_language="cs",
        )
