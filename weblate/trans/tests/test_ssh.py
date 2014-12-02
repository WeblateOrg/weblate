# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
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
import weblate.trans.ssh
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
            backup = weblate.trans.ssh.KNOWN_HOSTS_FILE
            weblate.trans.ssh.KNOWN_HOSTS_FILE = TEST_HOSTS
            hosts = weblate.trans.ssh.get_host_keys()
            self.assertEqual(len(hosts), 50)
        finally:
            weblate.trans.ssh.KNOWN_HOSTS_FILE = backup

    def test_create_ssh_wrapper(self):
        try:
            backup_dir = appsettings.DATA_DIR
            appsettings.DATA_DIR = os.path.join(self._tempdir)
            filename = os.path.join(
                appsettings.DATA_DIR, 'ssh', 'ssh-weblate-wrapper'
            )
            weblate.trans.ssh.create_ssh_wrapper()
            with open(filename, 'r') as handle:
                self.assertTrue(
                    weblate.trans.ssh.KNOWN_HOSTS_FILE in handle.read()
                )
            self.assertTrue(
                os.access(filename, os.X_OK)
            )
        finally:
            appsettings.DATA_DIR = backup_dir
