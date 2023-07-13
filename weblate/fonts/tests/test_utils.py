# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for fonts."""

from django.test import SimpleTestCase

from weblate.fonts.utils import check_render_size, get_font_weight


class RenderTest(SimpleTestCase):
    def test_render(self):
        self.assertTrue(
            check_render_size("sans", get_font_weight("normal"), 12, 0, "ahoj", 100, 1)
        )
        self.assertFalse(
            check_render_size("sans", get_font_weight("normal"), 12, 0, "ahoj", 10, 1)
        )
