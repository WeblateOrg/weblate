# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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

"""
Tests for unitdata models.
"""

from django.test import TestCase
from weblate.lang.models import Language
from weblate.trans.models import Check, Project


class UnitdataTestCase(TestCase):
    def setUp(self):
        super(UnitdataTestCase, self).setUp()
        self.project = Project.objects.create(name='test')

    def create_check(self, name):
        language = Language.objects.get(code='ach')
        return Check.objects.create(
            project=self.project,
            language=language,
            check=name,
            contentsum='123456'
        )

    def test_check(self):
        check = self.create_check('same')
        self.assertEqual(
            unicode(check.get_description()),
            u'Source and translated strings are same'
        )
        self.assertEqual(check.get_severity(), 'warning')
        self.assertTrue(
            check.get_doc_url().endswith('user/checks.html#check-same')
        )
        self.assertEqual(unicode(check), u'test/Acholi: same')

    def test_check_nonexisting(self):
        check = self.create_check('-invalid-')
        self.assertEqual(check.get_description(), '-invalid-')
        self.assertEqual(check.get_severity(), 'info')
        self.assertEqual(check.get_doc_url(), '')
