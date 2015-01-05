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

from unittest import TestCase
from weblate.trans.util import cleanup_repo_url
from weblate.trans.scripts import get_script_name


class HideCredentialsTest(TestCase):
    def test_http(self):
        self.assertEqual(
            cleanup_repo_url('http://foo:bar@example.com'),
            'http://example.com',
        )

    def test_http_user(self):
        self.assertEqual(
            cleanup_repo_url('http://foo@example.com'),
            'http://example.com',
        )

    def test_git(self):
        self.assertEqual(
            cleanup_repo_url('git://git.weblate.org/weblate.git'),
            'git://git.weblate.org/weblate.git',
        )

    def test_github(self):
        self.assertEqual(
            cleanup_repo_url('git@github.com:nijel/weblate.git'),
            'git@github.com:nijel/weblate.git',
        )

    def test_git_hg(self):
        self.assertEqual(
            cleanup_repo_url(
                'hg::https://bitbucket.org/sumwars/sumwars-code'
            ),
            'hg::https://bitbucket.org/sumwars/sumwars-code'
        )


class ScriptTest(TestCase):
    def test_full_path(self):
        self.assertEqual(
            get_script_name('/foo/bar/baz'),
            'baz'
        )

    def test_full_path_ext(self):
        self.assertEqual(
            get_script_name('/foo/bar/baz.sh'),
            'baz.sh'
        )

    def test_no_path(self):
        self.assertEqual(
            get_script_name('baz-script'),
            'baz-script'
        )
