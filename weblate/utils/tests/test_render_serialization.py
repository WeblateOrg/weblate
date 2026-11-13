# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ast
import json
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

from django.template import TemplateSyntaxError
from django.test import SimpleTestCase

from weblate.utils.render import (
    prepare_template_context,
    render_template,
)
from weblate.utils.render_context import validate_context
from weblate.utils.render_engine import RenderBudget, render_bounded
from weblate.utils.render_limits import OUTPUT_LIMIT
from weblate.utils.render_serialization import serialize
from weblate.utils.tests.render_reference import render_reference


class TemplateSerializationTest(SimpleTestCase):
    def assert_matches(self, source: str, value: object) -> str:
        context = prepare_template_context(source, {"value": value})
        expected = render_reference(source, context)
        actual = render_template(source, value=value)
        self.assertEqual(actual, expected)
        self.assertIs(type(actual), str)
        return actual

    def test_scalar_compatibility(self) -> None:
        for value in (
            None,
            True,
            False,
            0,
            -1,
            (1 << 4096) - 1,
            -0.0,
            1.25,
            1e-100,
            1e100,
            "",
            "'",
            '"',
            "'both\"",
            "\\\t\n\r\x00\x08\x0c\x1f\x7f",
            "Český 日本語 🙂\u2028\u2029\u200b\u00ad\u0378\U000e0001",
            date(2026, 1, 2),
            time(3, 4, 5, 123456),
            datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=UTC),
            datetime(2026, 1, 2, tzinfo=timezone(timedelta(hours=5, minutes=30))),
            Decimal("1.2300"),
            Decimal("1E+999999999"),
            Decimal("NaN"),
            UUID(int=0),
        ):
            for name in ("json", "python"):
                with self.subTest(value=value, name=name):
                    self.assert_matches("{{ value|" + name + " }}", value)

    def test_structured_compatibility(self) -> None:
        value = {
            "code": "cs",
            "stats": {
                "all": 3,
                "translated": 2,
                "last_changed": datetime(2026, 1, 1, tzinfo=UTC),
            },
            "nested": [{"enabled": True, "missing": None, "quoted": "a'b\\c"}, (1, 2)],
            "decimal": Decimal("1.25"),
            "uuid": UUID(int=0),
        }
        for name in ("json", "python"):
            for suffix in ("", "|escape", "|" + name):
                with self.subTest(name=name, suffix=suffix):
                    self.assert_matches("{{ value|" + name + suffix + " }}", value)

    def test_python_normalizes_tuples_and_rich_values_like_json(self) -> None:
        value = {
            "tuple": (1, None, True),
            "date": date(2026, 1, 1),
            "decimal": Decimal("1.25"),
        }
        result = self.assert_matches("{{ value|python }}", value)
        self.assertEqual(
            ast.literal_eval(result),
            {"tuple": [1, None, True], "date": "2026-01-01", "decimal": "1.25"},
        )

    def test_many_small_values(self) -> None:
        value = [None] * 100000
        for name in ("json", "python"):
            with self.subTest(name=name):
                text = self.assert_matches("{{ value|" + name + " }}", value)
                self.assertEqual(len(text), 600000)

    def test_expanded_results_are_rejected(self) -> None:
        for name, value in (
            ("json", "\x00" * (OUTPUT_LIMIT // 6 + 1)),
            ("json", "\x00" * (OUTPUT_LIMIT // 6) + "🙂"),
            ("python", "\x00" * (OUTPUT_LIMIT // 4)),
        ):
            with self.subTest(name=name), self.assertRaises(TemplateSyntaxError):
                render_template("{{ value|" + name + " }}", value=value)

    def test_valid_byte_boundaries(self) -> None:
        for name, value in (
            ("json", "a" * (OUTPUT_LIMIT - 2)),
            ("python", "a" * (OUTPUT_LIMIT - 2)),
            ("json", "\x00" * ((OUTPUT_LIMIT - 2) // 6)),
            ("python", "\x00" * ((OUTPUT_LIMIT - 2) // 4)),
        ):
            with self.subTest(name=name):
                text = self.assert_matches("{{ value|" + name + " }}", value)
                self.assertLessEqual(len(text.encode("utf-8")), OUTPUT_LIMIT)

    def test_python_container_preserves_json_intermediate_limit(self) -> None:
        value = "\x00" * 200000
        # The original Python filter allows a string whose temporary JSON is
        # larger, but rejects container inputs exceeding the JSON value limit.
        self.assert_matches("{{ value|python }}", value)
        for wrapped in ([value], {"data": value}):
            with (
                self.subTest(kind=type(wrapped)),
                self.assertRaises(TemplateSyntaxError),
            ):
                render_template("{{ value|python }}", value=wrapped)

    def test_unsupported_codec_values(self) -> None:
        for name in ("json", "python"):
            source = "{{ value|" + name + " }}"
            context = validate_context({"value": time(1, 2, tzinfo=UTC)})
            with self.subTest(name=name):
                with self.assertRaises(TemplateSyntaxError):
                    render_reference(source, context)
                with self.assertRaises(TemplateSyntaxError) as actual:
                    render_template(source, **context)
                self.assertEqual(
                    str(actual.exception),
                    f'Filter "{name}": Value or argument has an invalid format.',
                )

    def test_serialization_inside_control_flow(self) -> None:
        self.assert_matches(
            "{% if value|json %}{{ value|python }}{% endif %}", {"a": 1}
        )
        self.assert_matches(
            "{% for item in value %}{{ item|json }};{% endfor %}", [{"a": 1}, {"b": 2}]
        )
        source = "{% for item in items %}{% if value|json %}{% endif %}{% endfor %}"
        context = validate_context({"items": [0] * 10, "value": "x" * 20000})
        with (
            patch("weblate.utils.render_policy.WORK_LIMIT", 200000),
            self.assertRaises(TemplateSyntaxError),
        ):
            render_template(source, **context)

    def test_budget_failure_is_not_suppressed_by_conditions(self) -> None:
        source = "{% if value|python or True %}yes{% else %}no{% endif %}"
        with (
            patch("weblate.utils.render_policy.WORK_LIMIT", 1000),
            self.assertRaises(TemplateSyntaxError),
        ):
            render_bounded(source, {"value": list(range(100))})
        with self.assertRaises(TemplateSyntaxError):
            render_bounded(source, {"value": "\x00" * OUTPUT_LIMIT})
        self.assertEqual(render_bounded(source, {"value": "ok"}), "yes")

    def test_serialization_depth_and_state(self) -> None:
        value: object = None
        for _index in range(31):
            value = [value]
        self.assert_matches("{{ value|json }}", value)
        budget = RenderBudget()
        expected = json.dumps({"a": [1, True, None]}, ensure_ascii=False)
        self.assertEqual(
            serialize({"a": [1, True, None]}, budget, python=False), expected
        )

    def test_loop_metadata_can_extend_validated_context_depth(self) -> None:
        nested: object = None
        for _index in range(30):
            nested = [nested]
        source = "{% for a in items %}{% for b in items %}{{ forloop|json }}{% endfor %}{% endfor %}"
        context = prepare_template_context(
            source, {"items": [1], "forloop": {"deep": nested}}
        )
        expected = render_reference(source, context)
        self.assertEqual(render_template(source, **context), expected)
