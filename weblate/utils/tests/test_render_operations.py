# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import Mock, patch

from django.template import TemplateSyntaxError
from django.test import SimpleTestCase

from weblate.utils.render import (
    prepare_template_context,
    render_template,
)
from weblate.utils.render_context import validate_context
from weblate.utils.render_engine import RenderBudget, render_bounded
from weblate.utils.render_limits import OUTPUT_LIMIT
from weblate.utils.tests.render_reference import render_reference


class TemplateOperationsTest(SimpleTestCase):
    def assert_matches(self, source: str, values: dict[str, object]) -> None:
        expected = render_reference(source, prepare_template_context(source, values))
        self.assertEqual(render_template(source, **values), expected)

    def test_missing_conditions_and_loops(self) -> None:
        for source in (
            "{% if missing %}yes{% else %}no{% endif %}",
            "{% if data.missing %}yes{% else %}no{% endif %}",
            "{% if items.20 %}yes{% else %}no{% endif %}",
            "{% if items.invalid %}yes{% else %}no{% endif %}",
            "{% if nothing.missing %}yes{% else %}no{% endif %}",
            "{% if value|cut:missing %}yes{% else %}no{% endif %}",
            "{% if value|cut:missing or True %}yes{% else %}no{% endif %}",
            "{% if not value|cut:missing %}yes{% else %}no{% endif %}",
            "{% if not value|cut:missing or True %}yes{% else %}no{% endif %}",
            "{% for item in missing %}{{ item }}{% empty %}empty{% endfor %}",
            "{% for item in data.missing %}{{ item }}{% empty %}empty{% endfor %}",
        ):
            with self.subTest(source=source):
                self.assert_matches(
                    source, {"data": {}, "items": [1], "nothing": None, "value": "text"}
                )

    def test_undefined_values_preserve_errors(self) -> None:
        for expression in (
            "missing",
            "missing|default:'fallback'",
            "data.missing",
            "items.20",
            "items.invalid",
            "nothing.missing",
            "value|cut:missing",
            "2.",
        ):
            source = "{{ " + expression + " }}"
            context = prepare_template_context(
                source, {"data": {}, "items": [], "nothing": None, "value": "text"}
            )
            with self.subTest(source=source):
                with self.assertRaises(TemplateSyntaxError) as expected:
                    render_reference(source, context)
                with self.assertRaises(TemplateSyntaxError) as actual:
                    render_template(source, **context)
                if expression != "value|cut:missing":
                    self.assertEqual(str(actual.exception), str(expected.exception))
                else:
                    self.assertEqual(
                        str(actual.exception), "Undefined template variable."
                    )

    def test_sequence_indexing(self) -> None:
        for expression in (
            "items.0",
            "items.01",
            "text.1",
            "text.١",
            "nested.0.name",
            "data.0",
        ):
            with self.subTest(expression=expression):
                self.assert_matches(
                    "{{ " + expression + " }}",
                    {
                        "items": ["first", "second"],
                        "text": "Český",
                        "nested": [{"name": "value"}],
                        "data": {"0": "dictionary key"},
                    },
                )

    def test_read_only_dictionary_views(self) -> None:
        for source in (
            "{% for key,value in data.items %}{{ key }}={{ value }};{% empty %}empty{% endfor %}",
            "{% for key,value in data.items reversed %}{{ key }}={{ value }};{% endfor %}",
            "{% for key in data.keys %}{{ key }};{% endfor %}",
            "{% for value in data.values %}{{ value }};{% endfor %}",
            "{% for pair in data.items %}{{ pair.0 }}={{ pair.1 }};{% endfor %}",
            "{{ data.items|length }}:{{ data.keys|length }}:{{ data.values|length }}",
            "{{ data.keys|join:', ' }}:{{ data.values|join:', ' }}",
            "{% if data.items %}nonempty{% else %}empty{% endif %}",
        ):
            for data in ({}, {"a": "first", "b": "second"}):
                with self.subTest(source=source, data=data):
                    self.assert_matches(source, {"data": data})

    def test_dictionary_key_priority(self) -> None:
        for name in ("items", "keys", "values", "clear", "get"):
            with self.subTest(name=name):
                self.assert_matches(
                    "{{ data." + name + " }}", {"data": {name: "stored value"}}
                )

    def test_arbitrary_methods_are_rejected(self) -> None:
        for expression in (
            "data.clear",
            "data.copy",
            "data.get",
            "text.upper",
            "items.count",
        ):
            context = validate_context(
                {"data": {"key": "value"}, "items": ["text"], "text": "text"}
            )
            with self.subTest(expression=expression):
                with self.assertRaises(TemplateSyntaxError):
                    render_bounded("{% if " + expression + " %}yes{% endif %}", context)
                self.assertEqual(context["data"], {"key": "value"})

    def test_scalar_string_coercion(self) -> None:
        for value in (None, True, False, 123, -123, 1.25):
            for expression in (
                "value|upper",
                "value|lower",
                "value|capfirst",
                "value|title",
                "value|urlencode",
                "value|iriencode",
                "value|escape",
                "value|force_escape",
                "value|escapejs",
                "value|addslashes",
                "value|cut:'1'",
            ):
                with self.subTest(value=value, expression=expression):
                    self.assert_matches("{{ " + expression + " }}", {"value": value})
        with self.assertRaises(TemplateSyntaxError):
            render_bounded("{{ value|parentdir }}", {"value": 123})
        with self.assertRaises(TemplateSyntaxError):
            render_bounded("{{ value|upper }}", {"value": 1 << 5000})

    def test_sequence_filters(self) -> None:
        for items in ([], ["a", "b", "c"]):
            for source in (
                "{{ items|length }}:{{ items|first }}:{{ items|last }}",
                "{% for item in items|slice:':2' %}{{ item }}{% endfor %}",
                "{% for item in items|slice:'::-1' %}{{ item }}{% endfor %}",
                "{% for item in items|slice:1 %}{{ item }}{% endfor %}",
                "{% for item in items|slice:'::0' %}{{ item }}{% endfor %}",
                "{% for item in items|slice:'invalid' %}{{ item }}{% endfor %}",
                "{% for item in items|slice:'1:2:3:4' %}{{ item }}{% endfor %}",
                "{{ items|join:', ' }}",
            ):
                with self.subTest(source=source, items=items):
                    self.assert_matches(source, {"items": items})
        self.assert_matches("{{ data|length }}", {"data": {"a": 1}})
        self.assert_matches("{{ items|length }}", {"items": [0] * 20000})
        self.assert_matches("{% if items|first %}yes{% endif %}", {"items": [{"a": 1}]})
        self.assert_matches(
            "{% for a,b in data.items %}{{ a|first }}{{ b|last }}{% endfor %}",
            {"data": {"key": "value"}},
        )

    def test_join_types_and_escaping(self) -> None:
        self.assert_matches("{{ items|join:', '|escape }}", {"items": ["<b>", "&"]})
        self.assert_matches("{{ text|join:':' }}", {"text": "Český"})
        with self.assertRaises(TemplateSyntaxError):
            render_template("{{ items|join:',' }}", items=[1, 2])

    def test_replace(self) -> None:
        for source in (
            "{% replace value '-' '_' %}",
            "{% replace value|upper '-' '_' %}",
            "{% replace value '' 'é' %}",
            "{% replace value='a-b' char='-' replace_char='_' %}",
            "{% replace value '-' '_' as result %}{{ result }}",
            "{% if False %}{% replace invalid '-' '_' %}{% endif %}",
            "{% for value in items %}{% replace value '-' '_' as value %}{{ value }}{% endfor %}",
        ):
            with self.subTest(source=source):
                self.assert_matches(
                    source, {"value": "a-Č", "items": ["a-b", "c-d"], "invalid": 1}
                )
        with self.assertRaises(TemplateSyntaxError):
            render_bounded("{% replace value '-' '_' %}", {"value": 1})

    def test_assignment_does_not_modify_context(self) -> None:
        source = "{{ target }}|{% replace text '-' '_' as target %}{{ target }}"
        context = validate_context({"target": "original", "text": "a-b"})
        self.assertEqual(render_bounded(source, context), "original|a_b")
        self.assertEqual(context["target"], "original")

    def test_allocations_are_checked_before_filters(self) -> None:
        for name, value, args in (
            ("join", ["a", "b"], ("x" * OUTPUT_LIMIT,)),
            ("slice", [0] * 40000, (":",)),
        ):
            function = Mock()
            with self.subTest(name=name), self.assertRaises(TemplateSyntaxError):
                RenderBudget().apply_filter(
                    name, function, value, args, {"autoescape": False}
                )
            function.assert_not_called()
        source = "{% replace value '' replacement %}"
        with self.assertRaises(TemplateSyntaxError):
            render_template(source, value="ab", replacement="x" * (OUTPUT_LIMIT // 2))

    def test_operation_and_work_budgets(self) -> None:
        with self.assertRaises(TemplateSyntaxError):
            render_bounded("{{ items|join:',' }}", {"items": ["x"] * 10000})
        with (
            patch("weblate.utils.render_policy.WORK_LIMIT", 10),
            self.assertRaises(TemplateSyntaxError),
        ):
            render_bounded("{% replace value '-' '_' %}", {"value": "a-b"})
        self.assertEqual(
            render_bounded("{% replace value '-' '_' %}", {"value": "a-b"}), "a_b"
        )

    def test_index_length_is_bounded(self) -> None:
        source = "{% if items." + "9" * 129 + " %}yes{% else %}no{% endif %}"
        with self.assertRaises(TemplateSyntaxError):
            render_template(source, items=[1])
