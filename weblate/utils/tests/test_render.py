# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime

from django.test import SimpleTestCase
from django.utils.translation import override

from weblate.utils.render import render_template


class RenderTest(SimpleTestCase):
    def test_float(self) -> None:
        self.assertEqual(render_template("{{ number }}", number=1.1), "1.1")

    def test_float_cs(self) -> None:
        with override("cs"):
            self.test_float()

    def test_replace(self) -> None:
        self.assertEqual(
            render_template('{% replace "a-string-with-dashes" "-" " " %}'),
            "a string with dashes",
        )

    def test_dirname(self) -> None:
        self.assertEqual(
            render_template("{{ value|dirname }}", value="weblate/test.po"), "weblate"
        )

    def test_stripext(self) -> None:
        self.assertEqual(
            render_template("{{ value|stripext }}", value="weblate/test.po"),
            "weblate/test",
        )

    def test_parentdir(self) -> None:
        self.assertEqual(
            render_template("{{ value|parentdir }}", value="weblate/test.po"), "test.po"
        )

    def test_parentdir_chain(self) -> None:
        self.assertEqual(
            render_template(
                "{{ value|parentdir|parentdir }}", value="foo/bar/weblate/test.po"
            ),
            "weblate/test.po",
        )

    def test_serialization(self) -> None:
        value = {"name": 'Čeština "quoted" \n \\', "enabled": True, "missing": None}
        self.assertEqual(
            json.loads(render_template("{{ value|json }}", value=value)), value
        )
        self.assertEqual(
            ast.literal_eval(render_template("{{ value|python }}", value=value)), value
        )

    def test_serialization_datetime(self) -> None:
        value = {"last_change": datetime(2026, 1, 1, tzinfo=UTC)}
        expected = {"last_change": "2026-01-01T00:00:00Z"}
        self.assertEqual(
            json.loads(render_template("{{ value|json }}", value=value)), expected
        )
        self.assertEqual(
            ast.literal_eval(render_template("{{ value|python }}", value=value)),
            expected,
        )
