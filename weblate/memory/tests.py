#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from weblate_schemas import load_schema

from jsonschema import validate
from weblate.lang.models import Language
from weblate.memory.machine import WeblateMemory
from weblate.memory.models import Memory
from weblate.memory.utils import CATEGORY_FILE
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import get_test_file


def add_document():
    Memory.objects.create(
        source_language=Language.objects.get(code="en"),
        target_language=Language.objects.get(code="cs"),
        source="Hello",
        target="Ahoj",
        origin="test",
        from_file=True,
        shared=False,
    )


class MemoryModelTest(FixtureTestCase):
    def test_machine(self):
        add_document()
        unit = self.get_unit()
        machine_translation = WeblateMemory()
        self.assertEqual(
            machine_translation.translate(unit, search="Hello"),
            [
                {
                    "quality": 100,
                    "service": "Weblate Translation Memory",
                    "origin": "File: test",
                    "source": "Hello",
                    "text": "Ahoj",
                }
            ],
        )

    def test_import_tmx_command(self):
        call_command("import_memory", get_test_file("memory.tmx"))
        self.assertEqual(Memory.objects.count(), 2)

    def test_import_tmx2_command(self):
        call_command("import_memory", get_test_file("memory2.tmx"))
        self.assertEqual(Memory.objects.count(), 1)

    def test_import_map(self):
        call_command(
            "import_memory", get_test_file("memory.tmx"), language_map="en_US:en"
        )
        self.assertEqual(Memory.objects.count(), 2)

    def test_dump_command(self):
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

    def test_import_invalid_command(self):
        with self.assertRaises(CommandError):
            call_command("import_memory", get_test_file("cs.po"))
        self.assertEqual(Memory.objects.count(), 0)

    def test_import_json_command(self):
        call_command("import_memory", get_test_file("memory.json"))
        self.assertEqual(Memory.objects.count(), 1)

    def test_import_broken_json_command(self):
        with self.assertRaises(CommandError):
            call_command("import_memory", get_test_file("memory-broken.json"))
        self.assertEqual(Memory.objects.count(), 0)

    def test_import_empty_json_command(self):
        with self.assertRaises(CommandError):
            call_command("import_memory", get_test_file("memory-empty.json"))
        self.assertEqual(Memory.objects.count(), 0)


class MemoryViewTest(FixtureTestCase):
    def upload_file(self, name, **kwargs):
        with open(get_test_file(name), "rb") as handle:
            return self.client.post(
                reverse("memory-upload", **kwargs), {"file": handle}, follow=True
            )

    def test_memory(self, match="Number of your entries", fail=False, **kwargs):
        response = self.client.get(reverse("memory", **kwargs))
        self.assertContains(response, match)

        # Test upload
        response = self.upload_file("memory.tmx", **kwargs)
        if fail:
            self.assertContains(response, "Permission Denied", status_code=403)
        else:
            self.assertContains(response, "File processed")

        # Test download
        response = self.client.get(reverse("memory-download", **kwargs))
        validate(response.json(), load_schema("weblate-memory.schema.json"))

        # Test download
        response = self.client.get(
            reverse("memory-download", **kwargs), {"format": "tmx"}
        )
        self.assertContains(response, "<tmx")
        response = self.client.get(
            reverse("memory-download", **kwargs), {"format": "json"}
        )
        validate(response.json(), load_schema("weblate-memory.schema.json"))

        # Test invalid upload
        response = self.upload_file("cs.json", **kwargs)
        if fail:
            self.assertContains(response, "Permission Denied", status_code=403)
        else:
            self.assertContains(response, "Failed to parse JSON file")

        # Test invalid upload
        response = self.upload_file("memory-broken.json", **kwargs)
        if fail:
            self.assertContains(response, "Permission Denied", status_code=403)
        else:
            self.assertContains(response, "Failed to parse JSON file")

        # Test invalid upload
        response = self.upload_file("memory-invalid.json", **kwargs)
        if fail:
            self.assertContains(response, "Permission Denied", status_code=403)
        else:
            self.assertContains(response, "Failed to parse JSON file")

    def test_memory_project(self):
        self.test_memory("Number of entries for Test", True, kwargs=self.kw_project)

    def test_memory_project_superuser(self):
        self.user.is_superuser = True
        self.user.save()
        self.test_memory("Number of entries for Test", False, kwargs=self.kw_project)

    def test_global_memory_superuser(self):
        self.user.is_superuser = True
        self.user.save()
        self.test_memory(
            "Number of entries on the whole platform",
            False,
            kwargs={"manage": "manage"},
        )
        # Download all entries
        response = self.client.get(
            reverse("memory-download", kwargs={"manage": "manage"}),
            {"format": "json", "kind": "all"},
        )
        validate(response.json(), load_schema("weblate-memory.schema.json"))
        # Download shared entries
        response = self.client.get(
            reverse("memory-download", kwargs={"manage": "manage"}),
            {"format": "json", "kind": "shared"},
        )
        validate(response.json(), load_schema("weblate-memory.schema.json"))
