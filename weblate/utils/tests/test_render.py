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

from django.test import SimpleTestCase
from django.utils.translation import override

from weblate.utils.render import render_template


class RenderTest(SimpleTestCase):
    def test_float(self):
        self.assertEqual(
            render_template('{{ number }}', number=1.1),
            '1.1'
        )

    def test_float_cs(self):
        with override('cs'):
            self.test_float()

    def test_replace(self):
        self.assertEqual(
            render_template('{% replace "a-string-with-dashes" "-" " " %}'),
            'a string with dashes'
        )
