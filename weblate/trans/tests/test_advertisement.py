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
Tests for translation models.
"""

from django.test import TestCase
from django.utils import timezone
from weblate.trans.models import Advertisement
from weblate import appsettings
import datetime


class AdvertisementTest(TestCase):
    def test_none(self):
        appsettings.SELF_ADVERTISEMENT = False
        adv = Advertisement.objects.get_advertisement(
            Advertisement.PLACEMENT_MAIL_TEXT
        )
        self.assertIsNone(adv)

    def test_self(self):
        appsettings.SELF_ADVERTISEMENT = True
        adv = Advertisement.objects.get_advertisement(
            Advertisement.PLACEMENT_MAIL_TEXT
        )
        self.assertTrue('Weblate' in adv.text)

    def test_self_html(self):
        appsettings.SELF_ADVERTISEMENT = True
        adv = Advertisement.objects.get_advertisement(
            Advertisement.PLACEMENT_MAIL_HTML
        )
        self.assertTrue('Weblate' in adv.text)

    def test_existing(self):
        appsettings.SELF_ADVERTISEMENT = False
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

    def test_outdated(self):
        appsettings.SELF_ADVERTISEMENT = False
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
