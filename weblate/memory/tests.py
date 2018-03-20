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

from django.test import TestCase
from django.core.management import call_command

from weblate.lang.models import Language
from weblate.memory.machine import WeblateMemory
from weblate.memory.models import Memory
from weblate.trans.tests.utils import get_test_file
from weblate.trans.tests.test_checks import MockUnit


class MemoryTest(TestCase):
    def test_import(self):
        call_command(
            'import_memory',
            get_test_file('memory.tmx')
        )
        self.assertEqual(Memory.objects.count(), 2)

    def test_machine(self):
        Memory.objects.create(
            source_language=Language.objects.get(code='en'),
            target_language=Language.objects.get(code='cs'),
            source='Hello',
            target='Ahoj',
            origin='test'
        )
        machine_translation = WeblateMemory()
        self.assertEqual(
            machine_translation.translate('cs', 'Hello', MockUnit(), None),
            [
                {
                    'quality': 100,
                    'service': 'Weblate (test)',
                    'source': 'Hello',
                    'text': 'Ahoj'
                },
            ]
        )
