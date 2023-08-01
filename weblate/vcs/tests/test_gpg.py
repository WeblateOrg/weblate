# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import subprocess
from unittest import SkipTest

from django.core.cache import cache
from django.test import TestCase
from django.test.utils import override_settings
from packaging.version import Version

import weblate.vcs.gpg
from weblate.utils.checks import check_data_writable
from weblate.utils.unittest import tempdir_setting
from weblate.vcs.gpg import (
    generate_gpg_key,
    get_gpg_key,
    get_gpg_public_key,
    get_gpg_sign_key,
)


class GPGTest(TestCase):
    gpg_error = None

    @classmethod
    def setUpClass(cls):
        """Check whether we can use gpg."""
        super().setUpClass()
        try:
            result = subprocess.run(
                ["gpg", "--version"],
                check=True,
                text=True,
                capture_output=True,
            )
            version = result.stdout.splitlines()[0].strip().rsplit(None, 1)[-1]
            if Version(version) < Version("2.1"):
                cls.gpg_error = "gpg too old"
        except (subprocess.CalledProcessError, OSError):
            cls.gpg_error = "gpg not found"

    def setUp(self):
        if self.gpg_error:
            raise SkipTest(self.gpg_error)

    def check_errors(self):
        self.assertEqual(weblate.vcs.gpg.GPG_ERRORS, {})

    @tempdir_setting("DATA_DIR")
    @override_settings(
        WEBLATE_GPG_IDENTITY="Weblate <weblate@example.com>", WEBLATE_GPG_ALGO="rsa512"
    )
    def test_generate(self):
        self.assertEqual(check_data_writable(), [])
        self.assertIsNone(get_gpg_key(silent=True))
        key = generate_gpg_key()
        self.check_errors()
        self.assertIsNotNone(key)
        self.assertEqual(key, get_gpg_key())

    @tempdir_setting("DATA_DIR")
    @override_settings(
        WEBLATE_GPG_IDENTITY="Weblate <weblate@example.com>", WEBLATE_GPG_ALGO="rsa512"
    )
    def test_get(self):
        self.assertEqual(check_data_writable(), [])
        # This will generate new key
        key = get_gpg_sign_key()
        self.check_errors()
        self.assertIsNotNone(key)
        # Check cache access
        self.assertEqual(key, get_gpg_sign_key())
        # Check empty cache
        cache.delete("gpg-key-id")
        self.assertEqual(key, get_gpg_sign_key())

    @tempdir_setting("DATA_DIR")
    @override_settings(
        WEBLATE_GPG_IDENTITY="Weblate <weblate@example.com>", WEBLATE_GPG_ALGO="rsa512"
    )
    def test_public(self):
        self.assertEqual(check_data_writable(), [])
        # This will generate new key
        key = get_gpg_public_key()
        self.check_errors()
        self.assertIsNotNone(key)
        # Check cache access
        self.assertEqual(key, get_gpg_public_key())
