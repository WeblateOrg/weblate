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

from distutils.version import LooseVersion
import subprocess
from unittest import SkipTest

from django.core.cache import cache
from django.test import TestCase
from django.test.utils import override_settings

from weblate.vcs.gpg import (
    generate_gpg_key, get_gpg_key, get_gpg_sign_key, get_gpg_public_key,
)
from weblate.utils.checks import check_data_writable
from weblate.utils.unittest import tempdir_setting


class GPGTest(TestCase):
    gpg_error = None

    @classmethod
    def setUpClass(cls):
        """Check whether we can use gpg."""
        super(GPGTest, cls).setUpClass()
        try:
            output = subprocess.check_output(
                ['gpg', '--version'],
                stderr=subprocess.STDOUT,
            ).decode('utf-8')
            version = output.splitlines()[0].strip().rsplit(None, 1)[-1]
            if LooseVersion(version) < LooseVersion('2.1'):
                cls.gpg_error = 'gpg too old'
        except (subprocess.CalledProcessError, OSError):
            cls.gpg_error = 'gpg not found'

    def setUp(self):
        if self.gpg_error:
            raise SkipTest(self.gpg_error)

    @tempdir_setting('DATA_DIR')
    @override_settings(
        WEBLATE_GPG_IDENTITY='Weblate <weblate@example.com>',
        WEBLATE_GPG_ALGO='rsa512',
    )
    def test_generate(self):
        self.assertEqual(check_data_writable(), [])
        self.assertIsNone(get_gpg_key())
        key = generate_gpg_key()
        self.assertIsNotNone(key)
        self.assertEqual(key, get_gpg_key())

    @tempdir_setting('DATA_DIR')
    @override_settings(
        WEBLATE_GPG_IDENTITY='Weblate <weblate@example.com>',
        WEBLATE_GPG_ALGO='rsa512',
    )
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
    @override_settings(
        WEBLATE_GPG_IDENTITY='Weblate <weblate@example.com>',
        WEBLATE_GPG_ALGO='rsa512',
    )
    def test_public(self):
        self.assertEqual(check_data_writable(), [])
        # This will generate new key
        key = get_gpg_public_key()
        self.assertIsNotNone(key)
        # Check cache access
        self.assertEqual(key, get_gpg_public_key())
