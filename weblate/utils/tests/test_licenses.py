# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from pathlib import Path

from django.test import SimpleTestCase

from weblate.utils.licenses import detect_license


class LicenseDetectTestCase(SimpleTestCase):
    def test_none(self) -> None:
        self.assertIsNone(detect_license(Path(__file__)))

    def test_weblate(self) -> None:
        self.assertEqual(
            "GPL-3.0-only",
            detect_license(Path(__file__).parent.parent.parent.parent),
        )

    def test_threshold(self) -> None:
        # Because of too high threshold this ignores the LICENSE file
        # and picks one of the files in the LICENSES folder.
        self.assertEqual(
            "Apache-2.0",
            detect_license(Path(__file__).parent.parent.parent.parent, threshold=100),
        )
