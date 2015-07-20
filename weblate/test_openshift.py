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
"""OpenShift integration testing"""

from unittest import TestCase
import os
from weblate.openshiftlib import get_openshift_secret_key


class OpenShiftTest(TestCase):
    def test_key_missing(self):
        cleanup_vars = (
            'OPENSHIFT_APP_NAME',
            'OPENSHIFT_APP_UUID',
            'OPENSHIFT_SECRET_TOKEN'
        )
        for var in cleanup_vars:
            if var in os.environ:
                del os.environ[var]
        self.assertRaises(ValueError, get_openshift_secret_key)

    def test_key_stored(self):
        os.environ['OPENSHIFT_SECRET_TOKEN'] = 'TEST TOKEN'
        self.assertEqual(get_openshift_secret_key(), 'TEST TOKEN')
        del os.environ['OPENSHIFT_SECRET_TOKEN']

    def test_key_calc(self):
        os.environ['OPENSHIFT_APP_NAME'] = 'TOKEN'
        os.environ['OPENSHIFT_APP_UUID'] = 'TEST'
        self.assertEqual(
            get_openshift_secret_key(),
            '9cafcbef936068980e0ddefad417dcaea8c21020c68116bb74e3705ce3b62de4'
        )
        del os.environ['OPENSHIFT_APP_NAME']
        del os.environ['OPENSHIFT_APP_UUID']
