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

from django.conf import settings
from django.test import TestCase

from weblate.vcs.ssh import (
    get_host_keys, create_ssh_wrapper, ssh_file, get_wrapper_filename
)
from weblate.trans.tests.utils import get_test_file
from weblate.utils.data import check_data_writable
from weblate.utils.unittest import tempdir_setting


TEST_HOSTS = get_test_file('known_hosts')


class SSHTest(TestCase):
    """Test for customized admin interface."""
    @tempdir_setting('DATA_DIR')
    def test_parse(self):
        self.assertEqual(check_data_writable(), [])
        shutil.copy(TEST_HOSTS, os.path.join(settings.DATA_DIR, 'ssh'))
        hosts = get_host_keys()
        self.assertEqual(len(hosts), 50)

    @tempdir_setting('DATA_DIR')
    def test_create_ssh_wrapper(self):
        self.assertEqual(check_data_writable(), [])
        filename = get_wrapper_filename()
        create_ssh_wrapper()
        with open(filename, 'r') as handle:
            data = handle.read()
            self.assertTrue(ssh_file('known_hosts') in data)
            self.assertTrue(ssh_file('id_rsa') in data)
            self.assertTrue(settings.DATA_DIR in data)
        self.assertTrue(
            os.access(filename, os.X_OK)
        )
        # Second run should not touch the file
        timestamp = os.stat(filename).st_mtime
        create_ssh_wrapper()
        self.assertEqual(timestamp, os.stat(filename).st_mtime)
