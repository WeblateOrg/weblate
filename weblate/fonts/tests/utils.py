# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from weblate.fonts.models import FONT_STORAGE, Font
from weblate.trans.tests.test_views import FixtureTestCase

FONT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "static",
    "font-droid",
    "DroidSansFallback.ttf",
)


class FontTestCase(FixtureTestCase):
    def add_font(self):
        with open(FONT, "rb") as handle:
            fontfile = FONT_STORAGE.save("DroidSansFallback.ttf", handle)
        return Font.objects.create(font=fontfile, project=self.project, user=self.user)
