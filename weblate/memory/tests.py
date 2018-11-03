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

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.core.management import call_command
from django.core.management.base import CommandError

from six import StringIO

from weblate.memory.machine import WeblateMemory
from weblate.memory.storage import TranslationMemory, CATEGORY_FILE
from weblate.trans.tests.utils import get_test_file
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.checks.tests.test_checks import MockUnit

TEST_DOCUMENT = {
    'source_language': 'en',
    'target_language': 'cs',
    'source': 'Hello',
    'target': 'Ahoj',
    'origin': 'test',
    'category': CATEGORY_FILE,
}


def add_document():
    memory = TranslationMemory()
    with memory.writer() as writer:
        writer.add_document(**TEST_DOCUMENT)


class MemoryTest(SimpleTestCase):
    def setUp(self):
        TranslationMemory.cleanup()

    def test_import_invalid_command(self):
        with self.assertRaises(CommandError):
            call_command(
                'import_memory',
                get_test_file('cs.po')
            )
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 0)

    def test_import_json_command(self):
        call_command(
            'import_memory',
            get_test_file('memory.json')
        )
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 1)

    def test_import_broken_json_command(self):
        with self.assertRaises(CommandError):
            call_command(
                'import_memory',
                get_test_file('memory-broken.json')
            )
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 0)

    def test_import_empty_json_command(self):
        with self.assertRaises(CommandError):
            call_command(
                'import_memory',
                get_test_file('memory-empty.json')
            )
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 0)

    def test_dump_command(self):
        add_document()
        output = StringIO()
        call_command('dump_memory', stdout=output)
        data = json.loads(output.getvalue())
        self.assertEqual(data, [TEST_DOCUMENT])

    def test_delete_command_error(self):
        with self.assertRaises(CommandError):
            call_command('delete_memory')

    def test_delete_origin_command(self, params=None):
        if params is None:
            params = ['--origin', 'test']
        add_document()
        call_command('delete_memory', *params)
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 0)

    def test_delete_category_command(self):
        self.test_delete_origin_command(['--category', '1'])

    def test_delete_all_command(self):
        add_document()
        call_command('delete_memory', '--all')
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 0)

    def test_optimize_command(self):
        add_document()
        call_command('optimize_memory')
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 1)

    def test_rebuild_command(self):
        add_document()
        call_command('optimize_memory', '--rebuild')
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 1)

    def test_list_command(self):
        add_document()
        output = StringIO()
        call_command(
            'list_memory',
            stdout=output
        )
        self.assertIn('test', output.getvalue())

    def add_document(self):
        memory = TranslationMemory()
        with memory.writer() as writer:
            writer.add_document(**TEST_DOCUMENT)

    def test_delete(self):
        add_document()
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 1)
        self.assertEqual(memory.delete('test', None), 1)
        self.assertEqual(memory.delete('missing', None), 0)
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 0)

    def test_list(self):
        memory = TranslationMemory()
        self.assertEqual(memory.get_values('origin'), [])
        add_document()
        memory = TranslationMemory()
        self.assertEqual(memory.get_values('origin'), ['test'])


class MemoryDBTest(TestCase):
    def setUp(self):
        TranslationMemory.cleanup()

    def test_machine(self):
        add_document()
        machine_translation = WeblateMemory()
        self.assertEqual(
            machine_translation.translate('cs', 'Hello', MockUnit(), None),
            [
                {
                    'quality': 100,
                    'service': 'Weblate Translation Memory (File: test)',
                    'source': 'Hello',
                    'text': 'Ahoj'
                },
            ]
        )

    def test_import_tmx_command(self):
        call_command(
            'import_memory',
            get_test_file('memory.tmx')
        )
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 2)

    def test_import_tmx2_command(self):
        call_command(
            'import_memory',
            get_test_file('memory2.tmx')
        )
        memory = TranslationMemory()
        self.assertEqual(memory.doc_count(), 1)

    def test_import_map(self):
        call_command(
            'import_memory',
            get_test_file('memory.tmx'),
            language_map='en_US:en',
        )
        self.assertEqual(TranslationMemory().doc_count(), 2)


class MemoryViewTest(FixtureTestCase):
    def upload_file(self, name, **kwargs):
        with open(get_test_file(name), 'rb') as handle:
            return self.client.post(
                reverse('memory-upload', **kwargs),
                {'file': handle},
                follow=True
            )

    def test_memory(self, match='Number of your entries', fail=False,
                    **kwargs):
        response = self.client.get(reverse('memory-delete', **kwargs))
        self.assertRedirects(response, reverse('memory', **kwargs))

        response = self.client.post(reverse('memory-delete', **kwargs))
        self.assertRedirects(response, reverse('memory', **kwargs))

        response = self.client.get(reverse('memory', **kwargs))
        self.assertContains(response, match)

        # Test upload
        response = self.upload_file('memory.tmx', **kwargs)
        if fail:
            self.assertContains(response, 'Permission Denied', status_code=403)
        else:
            self.assertContains(response, 'File processed')

        # Test download
        response = self.client.get(reverse('memory-download', **kwargs))
        self.assertContains(response, '[')

        # Test download
        response = self.client.get(
            reverse('memory-download', **kwargs),
            {'format': 'tmx'}
        )
        self.assertContains(response, '<tmx')

        # Test wipe
        response = self.client.post(
            reverse('memory-delete', **kwargs),
            {'confirm': '1'},
            follow=True
        )
        if fail:
            self.assertContains(response, 'Permission Denied', status_code=403)
        else:
            self.assertContains(response, 'Entries deleted')

        # Test invalid upload
        response = self.upload_file('cs.json', **kwargs)
        if fail:
            self.assertContains(response, 'Permission Denied', status_code=403)
        else:
            self.assertContains(response, 'No valid entries found')

        # Test invalid upload
        response = self.upload_file('memory-broken.json', **kwargs)
        if fail:
            self.assertContains(response, 'Permission Denied', status_code=403)
        else:
            self.assertContains(response, 'Failed to parse JSON file')

    def test_memory_project(self):
        self.test_memory(
            'Number of entries for Test', True,
            kwargs=self.kw_project
        )

    def test_memory_project_superuser(self):
        self.user.is_superuser = True
        self.user.save()
        self.test_memory(
            'Number of entries for Test', False,
            kwargs=self.kw_project
        )

    def test_import(self):
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse('memory-import', kwargs=self.kw_project),
            {'confirm': '1'},
            follow=True
        )
        self.assertContains(response, 'Import of strings scheduled')
