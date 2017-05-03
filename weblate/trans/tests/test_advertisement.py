# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

import datetime

from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone

from weblate.trans.models import Advertisement


class AdvertisementTest(TestCase):
    @override_settings(SELF_ADVERTISEMENT=False)
    def test_none(self):
        adv = Advertisement.objects.get_advertisement(
            Advertisement.PLACEMENT_MAIL_TEXT
        )
        self.assertIsNone(adv)

    @override_settings(SELF_ADVERTISEMENT=True)
    def test_self(self):
        adv = Advertisement.objects.get_advertisement(
            Advertisement.PLACEMENT_MAIL_TEXT
        )
        self.assertTrue('Weblate' in adv.text)

    @override_settings(SELF_ADVERTISEMENT=True)
    def test_self_html(self):
        adv = Advertisement.objects.get_advertisement(
            Advertisement.PLACEMENT_MAIL_HTML
        )
        self.assertTrue('Weblate' in adv.text)

    @override_settings(SELF_ADVERTISEMENT=False)
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

    @override_settings(SELF_ADVERTISEMENT=False)
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
