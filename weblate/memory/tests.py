# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
from __future__ import unicode_literals

import json

from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError

from six import StringIO

from weblate.memory.machine import WeblateMemory
from weblate.memory.storage import TranslationMemory, CATEGORY_FILE
from weblate.trans.tests.utils import get_test_file
from weblate.checks.tests.test_checks import MockUnit

TEST_DOCUMENT = {
    'source_language': 'en',
    'target_language': 'cs',
    'source': 'Hello',
    'target': 'Ahoj',
    'origin': 'test',
    'category': CATEGORY_FILE,
}


class MemoryTest(TestCase):
    def setUp(self):
        TranslationMemory.cleanup()

    def test_import_tmx_command(self):
        call_command(
            'import_memory',
            get_test_file('memory.tmx')
        )
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 2)

    def test_import_json_command(self):
        call_command(
            'import_memory',
            get_test_file('memory.json')
        )
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 1)

    def test_dump_command(self):
        self.add_document()
        output = StringIO()
        call_command('dump_memory', stdout=output)
        data = json.loads(output.getvalue())
        self.assertEqual(data, [TEST_DOCUMENT])

    def test_delete_command_error(self):
        with self.assertRaises(CommandError):
            call_command('delete_memory')

    def test_delete_command(self):
        self.add_document()
        call_command('delete_memory', '--origin', 'test')
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 0)

    def test_delete_all_command(self):
        self.add_document()
        call_command('delete_memory', '--all')
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 0)

    def test_list_command(self):
        self.add_document()
        output = StringIO()
        call_command(
            'list_memory',
            stdout=output
        )
        self.assertIn('test', output.getvalue())

    def test_import_map(self):
        call_command(
            'import_memory',
            get_test_file('memory.tmx'),
            language_map='en_US:en',
        )
        self.assertEqual(TranslationMemory().doc_count(), 2)

    def add_document(self):
        memory = TranslationMemory()
        with memory.writer() as writer:
            writer.add_document(**TEST_DOCUMENT)

    def test_machine(self):
        self.add_document()
        machine_translation = WeblateMemory()
        self.assertEqual(
            machine_translation.translate('cs', 'Hello', MockUnit(), None),
            [
                {
                    'quality': 100,
                    'service': 'Weblate Translation Memory (test)',
                    'source': 'Hello',
                    'text': 'Ahoj'
                },
            ]
        )

    def test_delete(self):
        self.add_document()
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 1)
        self.assertEqual(memory.delete('test'), 1)
        self.assertEqual(memory.delete('missing'), 0)
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 0)

    def test_list(self):
        memory = TranslationMemory()
        self.assertEqual(list(memory.get_origins()), [])
        self.add_document()
        memory = TranslationMemory()
        self.assertEqual(memory.get_origins(), ['test'])
