# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

"""Test for translation models."""

from unittest import TestCase

from weblate.trans.templatetags.advertisement import (
    get_advertisement_text_mail,
    get_advertisement_html_mail,
)


class AdvertisementTest(TestCase):
    def test_text(self):
        self.assertIn(
            'https://',
            get_advertisement_text_mail()
        )

    def test_html(self):
        self.assertIn(
            'https://',
            get_advertisement_html_mail()
        )
