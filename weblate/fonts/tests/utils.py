# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from __future__ import annotations

from importlib import resources
from typing import TYPE_CHECKING

import weblate_fonts

from weblate.fonts.models import Font
from weblate.fonts.storage import font_storage
from weblate.trans.tests.test_views import FixtureComponentTestCase, FixtureTestCase

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable

    from weblate.auth.models import User
    from weblate.trans.models import Project

PACKAGE_PATH = resources.files(weblate_fonts)
FONT_DIR = PACKAGE_PATH / "static" / "weblate_fonts" / "kurinto" / "ttf"
FONT_NAME = "KurintoSans-Rg.ttf"
FONT = FONT_DIR / FONT_NAME
FONT_BOLD = FONT_DIR / "KurintoSans-Bd.ttf"

FONT_SOURCE_DIR = PACKAGE_PATH / "static" / "weblate_fonts" / "source-sans" / "ttf"
FONT_SOURCE = FONT_SOURCE_DIR / "SourceSans3-Bold.ttf"
FONT_SOURCE_ITALIC = FONT_SOURCE_DIR / "SourceSans3-It.ttf"
FONT_SOURCE_REGULAR = FONT_SOURCE_DIR / "SourceSans3-Regular.ttf"


class FontTestMixin:
    project: Project
    user: User

    def add_font(self, font: Traversable = FONT) -> Font:
        with font.open("rb") as handle:
            fontfile = font_storage.save(font.name, handle)
        return Font.objects.create(font=fontfile, project=self.project, user=self.user)


class FontComponentTestCase(FontTestMixin, FixtureComponentTestCase):
    pass


class FontTestCase(FontTestMixin, FixtureTestCase):
    pass
