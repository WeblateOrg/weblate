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

import tempfile
import os
import shutil
from django.test import TestCase
from weblate.trans.ssh import get_host_keys, create_ssh_wrapper, ssh_file
from weblate.trans.tests.utils import get_test_file
from weblate import appsettings


TEST_HOSTS = get_test_file('known_hosts')


class SSHTest(TestCase):
    '''
    Tests for customized admin interface.
    '''
    _tempdir = None

    def setUp(self):
        super(SSHTest, self).setUp()
        self._tempdir = tempfile.mkdtemp()

    def tearDown(self):
        if self._tempdir is not None:
            shutil.rmtree(self._tempdir)

    def test_parse(self):
        try:
            backup_dir = appsettings.DATA_DIR
            tempdir = os.path.join(self._tempdir, 'ssh')
            os.makedirs(tempdir)
            shutil.copy(TEST_HOSTS, tempdir)
            appsettings.DATA_DIR = self._tempdir
            hosts = get_host_keys()
            self.assertEqual(len(hosts), 50)
        finally:
            appsettings.DATA_DIR = backup_dir

    def test_create_ssh_wrapper(self):
        try:
            backup_dir = appsettings.DATA_DIR
            appsettings.DATA_DIR = self._tempdir
            filename = os.path.join(
                appsettings.DATA_DIR, 'ssh', 'ssh-weblate-wrapper'
            )
            create_ssh_wrapper()
            with open(filename, 'r') as handle:
                data = handle.read()
                self.assertTrue(ssh_file('known_hosts') in data)
                self.assertTrue(ssh_file('id_rsa') in data)
                self.assertTrue(self._tempdir in data)
            self.assertTrue(
                os.access(filename, os.X_OK)
            )
        finally:
            appsettings.DATA_DIR = backup_dir
