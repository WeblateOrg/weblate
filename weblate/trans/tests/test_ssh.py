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

import os
import shutil
from django.test import TestCase
from weblate.trans.ssh import get_host_keys, create_ssh_wrapper, ssh_file
from weblate.trans.tests.utils import get_test_file
from weblate.trans.tests import OverrideSettings
from weblate.trans.data import check_data_writable
from weblate import appsettings


TEST_HOSTS = get_test_file('known_hosts')


class SSHTest(TestCase):
    '''
    Tests for customized admin interface.
    '''
    @OverrideSettings(DATA_DIR=OverrideSettings.TEMP_DIR)
    def test_parse(self):
        check_data_writable()
        shutil.copy(TEST_HOSTS, os.path.join(appsettings.DATA_DIR, 'ssh'))
        hosts = get_host_keys()
        self.assertEqual(len(hosts), 50)

    @OverrideSettings(DATA_DIR=OverrideSettings.TEMP_DIR)
    def test_create_ssh_wrapper(self):
        check_data_writable()
        filename = os.path.join(
            appsettings.DATA_DIR, 'ssh', 'ssh-weblate-wrapper'
        )
        create_ssh_wrapper()
        with open(filename, 'r') as handle:
            data = handle.read()
            self.assertTrue(ssh_file('known_hosts') in data)
            self.assertTrue(ssh_file('id_rsa') in data)
            self.assertTrue(appsettings.DATA_DIR in data)
        self.assertTrue(
            os.access(filename, os.X_OK)
        )
