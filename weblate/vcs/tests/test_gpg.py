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

import os
import shutil
from unittest import SkipTest

from django.core.cache import cache
from django.test import TestCase
from django.test.utils import override_settings

from weblate.vcs.gpg import (
    generate_gpg_key, get_gpg_key, is_gpg_supported, get_gpg_sign_key,
    get_gpg_public_key,
)
from weblate.utils.data import check_data_writable
from weblate.utils.unittest import tempdir_setting


class GPGTest(TestCase):
    def setUp(self):
        if not is_gpg_supported():
            raise SkipTest('gpg not found')

    @tempdir_setting('DATA_DIR')
    @override_settings(WEBLATE_GPG_IDENTITY='Weblate <weblate@example.com>')
    def test_generate(self):
        self.assertEqual(check_data_writable(), [])
        self.assertIsNone(get_gpg_key())
        key = generate_gpg_key()
        self.assertIsNotNone(key)
        self.assertEqual(key, get_gpg_key())

    @tempdir_setting('DATA_DIR')
    @override_settings(WEBLATE_GPG_IDENTITY='Weblate <weblate@example.com>')
    def test_get(self):
        self.assertEqual(check_data_writable(), [])
        # This will generate new key
        key = get_gpg_sign_key()
        self.assertIsNotNone(key)
        # Check cache access
        self.assertEqual(key, get_gpg_sign_key())
        # Check empty cache
        cache.delete('gpg-key-id')
        self.assertEqual(key, get_gpg_sign_key())


    @tempdir_setting('DATA_DIR')
    @override_settings(WEBLATE_GPG_IDENTITY='Weblate <weblate@example.com>')
    def test_public(self):
        self.assertEqual(check_data_writable(), [])
        # This will generate new key
        key = get_gpg_public_key()
        self.assertIsNotNone(key)
        # Check cache access
        self.assertEqual(key, get_gpg_public_key())
