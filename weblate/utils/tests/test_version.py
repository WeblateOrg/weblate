# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import responses
from django.test import SimpleTestCase

from weblate.trans.tests.utils import get_test_file
from weblate.utils.version import (
    PYPI,
    download_version_info,
    flush_version_cache,
    get_latest_version,
    get_version_info,
)


class VersionTest(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        flush_version_cache()

    @staticmethod
    def mock_pypi() -> None:
        with open(get_test_file("pypi.json")) as handle:
            responses.add(responses.GET, PYPI, body=handle.read())

    @responses.activate
    def test_download(self) -> None:
        self.mock_pypi()
        data = download_version_info()
        self.assertEqual(len(data), 47)

    @responses.activate
    def test_get(self) -> None:
        self.mock_pypi()
        data = get_version_info()
        self.assertEqual(len(data), 47)
        responses.replace(responses.GET, PYPI, body="")
        data = get_version_info()
        self.assertEqual(len(data), 47)

    @responses.activate
    def test_latest(self) -> None:
        self.mock_pypi()
        latest = get_latest_version()
        self.assertEqual(latest.version, "3.10.3")
