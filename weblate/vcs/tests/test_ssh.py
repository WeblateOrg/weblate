# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import shutil

from django.conf import settings
from django.test import TestCase
from django.test.utils import override_settings

from weblate.trans.tests.utils import get_test_file
from weblate.utils.apps import check_data_writable
from weblate.utils.unittest import tempdir_setting
from weblate.vcs.ssh import SSHWrapper, get_host_keys, ssh_file

TEST_HOSTS = get_test_file("known_hosts")


class SSHTest(TestCase):
    """Test for customized admin interface."""

    @tempdir_setting("DATA_DIR")
    def test_parse(self) -> None:
        self.assertEqual(check_data_writable(app_configs=None, databases=None), [])
        shutil.copy(TEST_HOSTS, os.path.join(settings.DATA_DIR, "ssh"))
        hosts = get_host_keys()
        self.assertEqual(len(hosts), 50)

    @tempdir_setting("DATA_DIR")
    def test_create_ssh_wrapper(self) -> None:
        self.assertEqual(check_data_writable(app_configs=None, databases=None), [])
        wrapper = SSHWrapper()
        filename = wrapper.filename
        wrapper.create()
        with open(filename) as handle:
            data = handle.read()
            self.assertIn(ssh_file("known_hosts").as_posix(), data)
            self.assertIn(ssh_file("id_rsa").as_posix(), data)
            self.assertIn(settings.DATA_DIR, data)
        self.assertTrue(os.access(filename, os.X_OK))
        # Second run should not touch the file
        timestamp = os.stat(filename).st_mtime
        wrapper.create()
        self.assertEqual(timestamp, os.stat(filename).st_mtime)

    @tempdir_setting("DATA_DIR")
    @override_settings(SSH_EXTRA_ARGS="-oKexAlgorithms=+diffie-hellman-group1-sha1")
    def test_ssh_args(self) -> None:
        wrapper = SSHWrapper()
        filename = wrapper.filename
        wrapper.create()
        with open(filename) as handle:
            data = handle.read()
            self.assertIn(settings.SSH_EXTRA_ARGS, data)
        self.assertTrue(os.access(filename, os.X_OK))
        # Second run should not touch the file
        timestamp = os.stat(filename).st_mtime
        wrapper.create()
        self.assertEqual(timestamp, os.stat(filename).st_mtime)
