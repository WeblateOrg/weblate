# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import SimpleTestCase
from django.utils.translation import override

from weblate.utils.render import render_template


class RenderTest(SimpleTestCase):
    def test_float(self):
        self.assertEqual(render_template("{{ number }}", number=1.1), "1.1")

    def test_float_cs(self):
        with override("cs"):
            self.test_float()

    def test_replace(self):
        self.assertEqual(
            render_template('{% replace "a-string-with-dashes" "-" " " %}'),
            "a string with dashes",
        )

    def test_dirname(self):
        self.assertEqual(
            render_template("{{ value|dirname }}", value="weblate/test.po"), "weblate"
        )

    def test_stripext(self):
        self.assertEqual(
            render_template("{{ value|stripext }}", value="weblate/test.po"),
            "weblate/test",
        )

    def test_parentdir(self):
        self.assertEqual(
            render_template("{{ value|parentdir }}", value="weblate/test.po"), "test.po"
        )

    def test_parentdir_chain(self):
        self.assertEqual(
            render_template(
                "{{ value|parentdir|parentdir }}", value="foo/bar/weblate/test.po"
            ),
            "weblate/test.po",
        )
