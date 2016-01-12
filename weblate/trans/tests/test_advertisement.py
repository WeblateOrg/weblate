# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
Tests for translation models.
"""

import datetime

from django.test import TestCase
from django.utils import timezone

from weblate.trans.models import Advertisement
from weblate.trans.tests import OverrideSettings


class AdvertisementTest(TestCase):
    @OverrideSettings(SELF_ADVERTISEMENT=False)
    def test_none(self):
        adv = Advertisement.objects.get_advertisement(
            Advertisement.PLACEMENT_MAIL_TEXT
        )
        self.assertIsNone(adv)

    @OverrideSettings(SELF_ADVERTISEMENT=True)
    def test_self(self):
        adv = Advertisement.objects.get_advertisement(
            Advertisement.PLACEMENT_MAIL_TEXT
        )
        self.assertTrue('Weblate' in adv.text)

    @OverrideSettings(SELF_ADVERTISEMENT=True)
    def test_self_html(self):
        adv = Advertisement.objects.get_advertisement(
            Advertisement.PLACEMENT_MAIL_HTML
        )
        self.assertTrue('Weblate' in adv.text)

    @OverrideSettings(SELF_ADVERTISEMENT=False)
    def test_existing(self):
        adv_created = Advertisement.objects.create(
            placement=Advertisement.PLACEMENT_MAIL_TEXT,
            date_start=timezone.now(),
            date_end=timezone.now(),
            text='Test ADV'
        )
        adv = Advertisement.objects.get_advertisement(
            Advertisement.PLACEMENT_MAIL_TEXT
        )
        self.assertEqual(
            adv_created,
            adv
        )

    @OverrideSettings(SELF_ADVERTISEMENT=False)
    def test_outdated(self):
        Advertisement.objects.create(
            placement=Advertisement.PLACEMENT_MAIL_TEXT,
            date_start=timezone.now() - datetime.timedelta(days=1),
            date_end=timezone.now() - datetime.timedelta(days=1),
            text='Test ADV'
        )
        adv = Advertisement.objects.get_advertisement(
            Advertisement.PLACEMENT_MAIL_TEXT
        )
        self.assertIsNone(adv)
