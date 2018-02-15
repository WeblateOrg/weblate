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
"""Tests for hook scripts """

import os
import stat

from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.tests.utils import TempDirMixin
from weblate.trans.scripts import run_hook


class ScriptTest(RepoTestCase, TempDirMixin):
    output = None
    script = None

    def setUp(self):
        super(ScriptTest, self).setUp()
        self.create_temp()
        self.output = os.path.join(self.tempdir, 'output.log')
        self.script = os.path.join(self.tempdir, 'wrapper.sh')
        with open(self.script, 'wb') as handle:
            handle.write(b'#!/bin/sh\n')
            handle.write(b'echo "$WL_PATH" >> ')
            handle.write(self.output.encode('utf-8'))
            handle.write(b'\n')
        file_stat = os.stat(self.script)
        os.chmod(self.script, file_stat.st_mode | stat.S_IEXEC)

    def tearDown(self):
        super(ScriptTest, self).tearDown()
        self.remove_temp()
        self.output = None
        self.script = None

    def test_run_hook(self):
        subproject = self.create_subproject()
        self.assertFalse(
            run_hook(subproject, None, 'false')
        )
        self.assertTrue(
            run_hook(subproject, None, 'true')
        )

    def assert_content(self, subproject):
        """Check file content and cleans it."""
        with open(self.output, 'r') as handle:
            data = handle.read()
            self.assertIn(subproject.full_path, data)

        with open(self.output, 'w') as handle:
            handle.write('')

    def test_post_update(self):
        subproject = self._create_subproject(
            'po',
            'po/*.po',
            post_update_script=self.script
        )
        # Hook should fire on creation
        self.assert_content(subproject)

        subproject.update_branch()
        # Hook should fire on update
        self.assert_content(subproject)
