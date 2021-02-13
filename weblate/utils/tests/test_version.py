#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

import responses
from django.test import SimpleTestCase

from weblate.trans.tests.utils import get_test_file
from weblate.utils.checks import (
    PYPI,
    download_version_info,
    flush_version_cache,
    get_latest_version,
    get_version_info,
)


class VersionTest(SimpleTestCase):
    def setUp(self):
        super().setUp()
        flush_version_cache()

    @staticmethod
    def mock_pypi():
        with open(get_test_file("pypi.json")) as handle:
            responses.add(responses.GET, PYPI, body=handle.read())

    @responses.activate
    def test_download(self):
        self.mock_pypi()
        data = download_version_info()
        self.assertEqual(len(data), 47)

    @responses.activate
    def test_get(self):
        self.mock_pypi()
        data = get_version_info()
        self.assertEqual(len(data), 47)
        responses.replace(responses.GET, PYPI, body="")
        data = get_version_info()
        self.assertEqual(len(data), 47)

    @responses.activate
    def test_latest(self):
        self.mock_pypi()
        latest = get_latest_version()
        self.assertEqual(latest.version, "3.10.3")
