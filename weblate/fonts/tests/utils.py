# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from importlib import resources

import weblate_fonts

from weblate.fonts.models import FONT_STORAGE, Font
from weblate.trans.tests.test_views import FixtureTestCase

PACKAGE_PATH = resources.files(weblate_fonts)
FONT_DIR = PACKAGE_PATH / "static" / "weblate_fonts" / "kurinto" / "ttf"
FONT_NAME = "KurintoSans-Rg.ttf"
FONT = FONT_DIR / FONT_NAME
FONT_BOLD = FONT_DIR / "KurintoSans-Bd.ttf"

FONT_SOURCE = (
    PACKAGE_PATH
    / "static"
    / "weblate_fonts"
    / "source-sans"
    / "ttf"
    / "SourceSans3-Bold.ttf"
)


class FontTestCase(FixtureTestCase):
    def add_font(self):
        with FONT.open("rb") as handle:
            fontfile = FONT_STORAGE.save(FONT_NAME, handle)
        return Font.objects.create(font=fontfile, project=self.project, user=self.user)
