# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.test import TestCase
from trans.tests.views import ViewTestCase
from trans.models.unit import Unit
try:
    from unittest import skipUnless
except ImportError:
    from unittest2 import skipUnless
from trans.machine.dummy import DummyTranslation
from trans.machine.glosbe import GlosbeTranslation
from trans.machine.mymemory import MyMemoryTranslation
from trans.machine.opentran import OpenTranTranslation
from trans.machine.apertium import ApertiumTranslation
from trans.machine.tmserver import AmagamaTranslation
from trans.machine.microsoft import (
    MicrosoftTranslation, microsoft_translation_supported
)
from trans.machine.google import GoogleTranslation
from trans.machine.weblatetm import (
    WeblateSimilarTranslation, WeblateTranslation
)


class MachineTranslationTest(TestCase):
    '''
    Testing of machine translation core.
    '''
    def test_support(self):
        machine_translation = DummyTranslation()
        self.assertTrue(machine_translation.is_supported('cs'))
        self.assertFalse(machine_translation.is_supported('de'))

    def test_translate(self):
        machine_translation = DummyTranslation()
        self.assertEqual(
            machine_translation.translate('cs', 'Hello', None),
            []
        )
        self.assertEqual(
            len(machine_translation.translate('cs', 'Hello, world!', None)),
            2
        )

    def test_glosbe(self):
        machine = GlosbeTranslation()
        self.assertIsInstance(machine.translate('cs', 'world', None), list)

    def test_mymemory(self):
        machine = MyMemoryTranslation()
        self.assertIsInstance(machine.translate('cs', 'world', None), list)

    def test_opentran(self):
        machine = OpenTranTranslation()
        self.assertIsInstance(machine.translate('cs', 'world', None), list)

    def test_apertium(self):
        machine = ApertiumTranslation()
        self.assertIsInstance(machine.translate('es', 'world', None), list)

    @skipUnless(microsoft_translation_supported(),
                         'missing credentials')
    def test_microsoft(self):
        machine = MicrosoftTranslation()
        self.assertIsInstance(machine.translate('cs', 'world', None), list)

    def test_google(self):
        machine = GoogleTranslation()
        self.assertIsInstance(machine.translate('cs', 'world', None), list)

    def test_amagama(self):
        machine = AmagamaTranslation()
        self.assertIsInstance(machine.translate('cs', 'world', None), list)


class WeblateTranslationTest(ViewTestCase):
    def test_same(self):
        machine = WeblateTranslation()
        unit = Unit.objects.all()[0]
        results = machine.translate(
            unit.translation.language.code,
            unit.get_source_plurals()[0],
            unit
        )
        self.assertEquals(results, [])

    def test_similar(self):
        machine = WeblateSimilarTranslation()
        unit = Unit.objects.all()[0]
        results = machine.translate(
            unit.translation.language.code,
            unit.get_source_plurals()[0],
            unit
        )
        self.assertEquals(results, [])
