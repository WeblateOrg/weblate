# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from pathlib import Path

from weblate.fonts.models import FONT_STORAGE, Font
from weblate.trans.tests.test_views import FixtureTestCase

FONT_DIR = Path(__file__).parent.parent.parent / "static" / "vendor" / "font-kurinto"
FONT_NAME = "KurintoSans-Rg.ttf"
FONT = FONT_DIR / FONT_NAME
FONT_BOLD = FONT_DIR / "KurintoSans-Bd.ttf"


class FontTestCase(FixtureTestCase):
    def add_font(self):
        with FONT.open("rb") as handle:
            fontfile = FONT_STORAGE.save(FONT_NAME, handle)
        return Font.objects.create(font=fontfile, project=self.project, user=self.user)
