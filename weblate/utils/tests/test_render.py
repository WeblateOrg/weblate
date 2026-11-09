# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ast
import json
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import tempfile
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.template import TemplateSyntaxError
from django.test import SimpleTestCase
from django.utils.html import conditional_escape
from django.utils.timezone import override as override_timezone
from django.utils.translation import override

from weblate.utils.render import render_template, validate_render
from weblate.utils.render_worker import (
    CONTEXT_LIMIT,
    LOOP_LIMIT,
    OUTPUT_LIMIT,
    SOURCE_LIMIT,
)


class RenderTest(SimpleTestCase):
    def test_output_is_plain_text(self) -> None:
        rendered = render_template("<b>{{ value }}</b>", value="text")
        self.assertEqual(rendered, "<b>text</b>")
        self.assertEqual(conditional_escape(rendered), "&lt;b&gt;text&lt;/b&gt;")

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

    def test_source_byte_limit(self) -> None:
        source = "é" * (SOURCE_LIMIT // 2)
        self.assertEqual(render_template(source), source)
        with self.assertRaises(TemplateSyntaxError):
            render_template(source + "é")
        with self.assertRaises(ValidationError):
            validate_render(source + "é")

    def test_simple_substitutions_do_not_start_worker(self) -> None:
        with patch("weblate.utils.render.subprocess.run") as run:
            self.assertEqual(
                render_template(
                    "{{ branch }}/{{ filename }}:{{ line }}",
                    branch="main",
                    filename="cs.po",
                    line=9,
                ),
                "main/cs.po:9",
            )
        run.assert_not_called()

    def test_simple_and_isolated_scalar_formatting(self) -> None:
        for value in (None, True, False, 1234, 1.25, "<b>text</b>"):
            with self.subTest(value=value):
                self.assertEqual(
                    render_template("{{ value }}", value=value),
                    render_template("{% if True %}{{ value }}{% endif %}", value=value),
                )

    def test_multiline_variable_remains_literal(self) -> None:
        self.assertEqual(render_template("{{\nvalue}}", value="text"), "{{\nvalue}}")

    def test_unknown_variables_and_tags(self) -> None:
        for source in ("{{ missing }}", "{% include 'file' %}", "{% load static %}"):
            with self.subTest(source=source), self.assertRaises(TemplateSyntaxError):
                render_template(source)

    def test_loop_limit(self) -> None:
        template = "{% for value in values %}x{% endfor %}"
        self.assertEqual(
            render_template(template, values=[0] * LOOP_LIMIT), "x" * LOOP_LIMIT
        )
        with self.assertRaisesMessage(TemplateSyntaxError, "loop limit"):
            render_template(template, values=[0] * (LOOP_LIMIT + 1))

    def test_nested_and_sibling_loops_share_budget(self) -> None:
        for template in (
            "{% for a in values %}{% for b in values %}x{% endfor %}{% endfor %}",
            "{% for a in values %}{% endfor %}{% for a in values %}{% endfor %}",
        ):
            with (
                self.subTest(template=template),
                self.assertRaisesMessage(TemplateSyntaxError, "loop limit"),
            ):
                render_template(template, values=[0] * (LOOP_LIMIT // 2 + 1))

    def test_loop_semantics(self) -> None:
        self.assertEqual(
            render_template(
                "{% for a,b in values reversed %}{{ forloop.counter }}:{{ a }}={{ b }};{% empty %}empty{% endfor %}",
                values=[("a", 1), ("b", 2)],
            ),
            "1:b=2;2:a=1;",
        )
        self.assertEqual(
            render_template(
                "{% for a in values %}x{% empty %}empty{% endfor %}", values=[]
            ),
            "empty",
        )
        self.assertEqual(
            render_template(
                "{% for a in values %}{% for b in values %}{{ forloop.parentloop.counter }}{{ forloop.counter }}{% endfor %}{% endfor %}",
                values=[1, 2],
            ),
            "11122122",
        )

    def test_output_byte_limit(self) -> None:
        value = "é" * (OUTPUT_LIMIT // 2)
        for template in ("{{ value }}", "{% if True %}{{ value }}{% endif %}"):
            with self.subTest(template=template):
                self.assertEqual(render_template(template, value=value), value)
                with self.assertRaises(TemplateSyntaxError):
                    render_template(template, value=value + "é")
                with self.assertRaises(TemplateSyntaxError):
                    render_template(template + "x", value=value)

    def test_loop_output_limit(self) -> None:
        with self.assertRaises(TemplateSyntaxError):
            render_template(
                "{% for a in values %}{{ text }}{% endfor %}",
                values=[1, 2],
                text="x" * (OUTPUT_LIMIT // 2 + 1),
            )

    def test_expanding_filters(self) -> None:
        for name in ("center", "ljust", "rjust", "floatformat", "stringformat"):
            with self.subTest(filter=name), self.assertRaises(TemplateSyntaxError):
                render_template("{{ value|" + name + ':"1048577" }}', value=1)
        with self.assertRaises(TemplateSyntaxError):
            render_template(
                "{{ values|join:separator }}",
                values=["a", "b", "c"],
                separator="x" * (OUTPUT_LIMIT // 2),
            )
        with self.assertRaises(TemplateSyntaxError):
            render_template(
                '{% replace value "" replacement %}',
                value="ab",
                replacement="x" * (OUTPUT_LIMIT // 2),
            )
        for name in ("json", "python"):
            with self.subTest(filter=name), self.assertRaises(TemplateSyntaxError):
                render_template(
                    "{{ value|" + name + "|" + name + " }}",
                    value="\\" * (OUTPUT_LIMIT // 4),
                )

    def test_context_types(self) -> None:
        self.assertEqual(
            render_template(
                '{{ value.date|date:"Y-m-d" }} {{ value.time|time:"H:i" }} {{ value.decimal|floatformat:2 }}',
                value={
                    "date": date(2026, 1, 2),
                    "time": time(12, 34),
                    "decimal": Decimal("1.25"),
                },
            ),
            "2026-01-02 12:34 1.25",
        )

    def test_context_limits(self) -> None:
        value: object = "text"
        for _index in range(34):
            value = [value]
        for context in (value, object(), "x" * (CONTEXT_LIMIT + 1)):
            with (
                self.subTest(context_type=type(context)),
                self.assertRaises(TemplateSyntaxError),
            ):
                render_template("{{ value|length }}", value=context)

    def test_deadline_kills_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            worker = Path(directory) / "worker.py"
            worker.write_text(
                "import os, time\nprint(os.getpid(), flush=True)\ntime.sleep(2)\n",
                encoding="utf-8",
            )
            with (
                patch("weblate.utils.render.Path.with_name", return_value=worker),
                patch("weblate.utils.render.RENDER_TIMEOUT", 0.5),
                self.assertRaisesMessage(
                    TemplateSyntaxError, "resource limits"
                ) as raised,
            ):
                render_template("{{ value|upper }}", value="text")
        cause = raised.exception.__cause__
        self.assertIsInstance(cause, subprocess.TimeoutExpired)
        assert isinstance(cause, subprocess.TimeoutExpired)
        assert cause.output
        pid = int(cause.output.strip())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)
        self.assertEqual(render_template("{{ value|upper }}", value="text"), "TEXT")

    def test_current_timezone(self) -> None:
        with override_timezone("Europe/Prague"):
            self.assertEqual(
                render_template(
                    '{{ value|date:"H:i" }}', value=datetime(2026, 1, 1, tzinfo=UTC)
                ),
                "01:00",
            )
