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
"""OpenShift integration testing"""

from unittest import TestCase
import os

from django.conf import Settings

from weblate.openshiftlib import get_openshift_secret_key, import_env_vars


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

    def test_import_env_string(self):
        storage = Settings('weblate.settings_example')
        import_env_vars({'WEBLATE_FOO': '"bar"'}, storage)
        self.assertEqual(storage.FOO, 'bar')

    def test_import_env_int(self):
        storage = Settings('weblate.settings_example')
        import_env_vars({'WEBLATE_FOO': '1234'}, storage)
        self.assertEqual(storage.FOO, 1234)

    def test_import_env_tuple(self):
        storage = Settings('weblate.settings_example')
        import_env_vars({'WEBLATE_FOO': '(1, 2)'}, storage)
        self.assertEqual(storage.FOO, (1, 2))

    def test_import_env_env(self):
        storage = Settings('weblate.settings_example')
        import_env_vars({'WEBLATE_FOO': '"$BAR"', 'BAR': 'baz'}, storage)
        self.assertEqual(storage.FOO, 'baz')

    def test_import_env_raw(self):
        storage = Settings('weblate.settings_example')
        import_env_vars({'WEBLATE_FOO': '(r"/project/(.*)$$",)'}, storage)
        self.assertEqual(storage.FOO, ('/project/(.*)$',))
