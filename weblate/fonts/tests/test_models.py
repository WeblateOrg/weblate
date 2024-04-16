# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from weblate.fonts.models import FONT_STORAGE
from weblate.fonts.tasks import cleanup_font_files
from weblate.fonts.tests.utils import FontTestCase
from weblate.fonts.utils import configure_fontconfig


class FontModelTest(FontTestCase):
    def test_save(self) -> None:
        font = self.add_font()
        self.assertEqual(font.family, "Kurinto Sans")
        self.assertEqual(font.style, "Regular")

    def assert_font_files(self, expected: int) -> None:
        result = 0
        excluded = {"fonts.conf", ".uuid"}
        for name in FONT_STORAGE.listdir(".")[1]:
            if name not in excluded:
                result += 1
        self.assertEqual(result, expected)

    def test_cleanup(self) -> None:
        configure_fontconfig()
        cleanup_font_files()
        self.assert_font_files(0)
        font = self.add_font()
        self.assert_font_files(1)
        cleanup_font_files()
        self.assert_font_files(1)
        font.delete()
        self.assert_font_files(1)
        cleanup_font_files()
        self.assert_font_files(0)
