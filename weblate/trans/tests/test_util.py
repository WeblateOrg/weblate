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

from unittest import TestCase
from weblate.trans.util import cleanup_repo_url, translation_percent


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
            cleanup_repo_url('git@github.com:WeblateOrg/weblate.git'),
            'git@github.com:WeblateOrg/weblate.git',
        )

    def test_git_hg(self):
        self.assertEqual(
            cleanup_repo_url(
                'hg::https://bitbucket.org/sumwars/sumwars-code'
            ),
            'hg::https://bitbucket.org/sumwars/sumwars-code'
        )


class TranslationPercentTest(TestCase):
    def test_common(self):
        self.assertAlmostEqual(translation_percent(2, 4), 50.0)

    def test_empty(self):
        self.assertAlmostEqual(translation_percent(0, 0), 100.0)

    def test_none(self):
        self.assertAlmostEqual(translation_percent(0, None), 0.0)

    def test_untranslated_file(self):
        self.assertAlmostEqual(translation_percent(0, 100), 0.0)

    def test_almost_untranslated_file(self):
        self.assertAlmostEqual(translation_percent(1, 10000000000), 0.1)

    def test_translated_file(self):
        self.assertAlmostEqual(translation_percent(100, 100), 100.0)

    def test_almost_translated_file(self):
        self.assertAlmostEqual(translation_percent(99999999, 100000000), 99.9)
