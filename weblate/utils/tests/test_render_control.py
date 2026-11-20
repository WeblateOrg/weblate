# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch

from django.template import TemplateSyntaxError
from django.test import SimpleTestCase

from weblate.addons.forms import DiscoveryForm, GenerateMoForm
from weblate.trans.defaults import DEFAULT_PULL_MESSAGE
from weblate.utils.render import (
    prepare_template_context,
    render_template,
)
from weblate.utils.render_context import validate_context
from weblate.utils.render_engine import RenderBudget, render_bounded
from weblate.utils.render_limits import LOOP_LIMIT, OUTPUT_LIMIT
from weblate.utils.tests.render_reference import render_reference


class TemplateControlFlowTest(SimpleTestCase):
    def assert_matches(self, source: str, values: dict[str, object]) -> None:
        context = prepare_template_context(source, values)
        expected = render_reference(source, context)
        self.assertEqual(render_template(source, **values), expected)

    def test_discovery_and_filename_defaults(self) -> None:
        sources = {preset["name_template"] for preset in DiscoveryForm.PRESETS.values()}
        sources.add(GenerateMoForm.base_fields["path"].initial)
        for source in sources:
            with self.subTest(source=source):
                self.assert_matches(
                    source,
                    {
                        "component": "messages",
                        "originalHierarchy": "backend",
                        "filename": "po/cs.po",
                    },
                )

    def test_default_pull_message(self) -> None:
        for children in (
            [],
            [{"full_name": "Project/Child", "url": "https://example.org/child/"}],
        ):
            with self.subTest(children=children):
                self.assert_matches(
                    DEFAULT_PULL_MESSAGE,
                    {
                        "component_full_name": "Project/Component",
                        "url": "https://example.org/",
                        "widget_url": "https://example.org/widget.svg",
                        "component_linked_children": children,
                    },
                )

    def test_conditions(self) -> None:
        for expression in (
            "items",
            "not items",
            "not not items",
            "items and value",
            "empty or value",
            "count > 1 and count <= 3",
            "count == 2",
            "count != 2",
            "value < other",
            "value|upper == 'TEXT'",
            "count > value",
            "nothing is None",
            "value is not None",
            "enabled is True",
            "disabled is False",
            "False and missing",
            "True or missing",
            "count >= 1.25",
            "count < 4",
        ):
            source = (
                "{% if "
                + expression
                + " %}first{% elif empty %}second{% else %}last{% endif %}"
            )
            with self.subTest(expression=expression):
                self.assert_matches(
                    source,
                    {
                        "items": [1],
                        "empty": [],
                        "value": "text",
                        "other": "zzz",
                        "count": 2,
                        "nothing": None,
                        "enabled": True,
                        "disabled": False,
                    },
                )

    def test_loop_semantics(self) -> None:
        sources = (
            "{% for item in items %}{{ item }}{% empty %}empty{% endfor %}",
            "{% for item in items reversed %}{{ forloop.counter }}:{{ item }};{% endfor %}",
            "{% for item in items %}{{ forloop.counter0 }}/{{ forloop.revcounter }}/{{ forloop.revcounter0 }}/{{ forloop.first }}/{{ forloop.last }};{% endfor %}",
            "{% for item in items %}{% for item in items %}{{ forloop.parentloop.counter }}:{{ item }};{% endfor %}{{ item }}{% endfor %}",
            "{{ item }}{% for item in items %}{{ item }}{% endfor %}{{ item }}",
            "{% for key,value in pairs reversed %}{{ key|upper }}={{ value }};{% empty %}empty{% endfor %}",
            "{% for item in items %}{% if item %}{{ item }}{% else %}zero{% endif %}{% endfor %}",
            "{% for key in mapping %}{{ key }}{% endfor %}",
        )
        for items in ([], [0, 1, 2], "abc"):
            for source in sources:
                with self.subTest(source=source, items=items):
                    self.assert_matches(
                        source,
                        {
                            "items": items,
                            "item": "outer",
                            "pairs": [["a", 1], ["b", 2]],
                            "mapping": {"a": 1, "b": 2},
                        },
                    )

    def test_unsupported_features_in_untaken_branches(self) -> None:
        for source in (
            "{% if False %}{{ value|pprint }}{% endif %}",
            "{% if False %}{% replace value|pprint 'x' 'y' %}{% endif %}",
            "{% for item in empty %}{{ item|pprint }}{% endfor %}",
            "{% if False %}x{% elif value in items %}y{% endif %}",
            "{% for item in items %}{{ item }}{% empty %}{{ value|pprint }}{% endfor %}",
        ):
            with (
                self.subTest(source=source),
                patch("weblate.utils.render_engine.RenderBudget.apply_filter") as apply,
                self.assertRaises(TemplateSyntaxError),
            ):
                render_bounded(source, {"value": "x", "items": [1], "empty": []})
            apply.assert_not_called()

    def test_unsupported_runtime_operations_fail_directly(self) -> None:
        for source, values in (
            ("{{ value.items }}", {"value": {"key": 1}}),
            ("{{ value.year }}", {"value": date(2026, 1, 1)}),
            ("{% if value == other %}yes{% endif %}", {"value": [1], "other": [1]}),
            (
                "{% if value is other %}yes{% endif %}",
                {"value": "text", "other": "text"},
            ),
            ("{% if value in items %}yes{% endif %}", {"value": "x", "items": ["x"]}),
        ):
            with self.subTest(source=source), self.assertRaises(TemplateSyntaxError):
                render_template(source, **values)

    def test_invalid_syntax_is_rejected(self) -> None:
        for source in (
            "{{ value._private }}",
            "{{ value|slice }}",
            '{{ value|upper:"x" }}',
            "{{ value|json:1 }}",
            "{{ value|python:1 }}",
            '{{ value|cut: "x" }}',
            '{{ value|cut:"unterminated }}',
            "{% for item items %}x{% endfor %}",
            "{% if True and %}x{% endif %}",
        ):
            with self.subTest(source=source), self.assertRaises(TemplateSyntaxError):
                render_template(source, value="text")

    def test_parse_limits_fail_before_compiling(self) -> None:
        sources = (
            "{{ value }}" * 1025,
            '{{ "' + "x" * 2049 + '" }}',
            "{% if True %}" * 33 + "x" + "{% endif %}" * 33,
            "{% if " + "not " * 65 + "True %}x{% endif %}",
            "{{ value" + "|lower" * 1025 + " }}",
            "{{ {{ {{ malformed }}",
            "{{ value\n }}",
            "{% include 'file' %}",
            '{# comment #}{{ "'
            + "x" * 2000
            + '" }}{{ "'
            + "y" * 2000
            + '" }}{{ "'
            + "z" * 2000
            + '" }}',
        )
        for source in sources:
            with (
                self.subTest(source=source[:60]),
                patch(
                    "weblate.utils.render_engine.RestrictedTemplate"
                ) as compile_template,
                self.assertRaises(TemplateSyntaxError),
            ):
                render_bounded(source, {"value": "text"})
            compile_template.assert_not_called()

    def test_comments_and_quoted_literals(self) -> None:
        self.assert_matches("before{# ignored #}{{ 'a|b:c'|upper }}after", {})

    def test_budgets_inside_conditions_are_not_swallowed(self) -> None:
        source = "{% for value in values %}{% if value|upper == other or enabled %}yes{% else %}no{% endif %}{% endfor %}suffix"
        values = {"values": ["text", "text"], "other": "TEXT", "enabled": True}
        for limit, threshold in (
            ("FILTER_LIMIT", 1),
            ("WORK_LIMIT", 1),
            ("OPERATION_LIMIT", 8),
        ):
            # Exercise runtime limits separately from the compilation guards.
            with (
                self.subTest(limit=limit),
                patch("weblate.utils.render_policy." + limit, threshold),
                patch.object(
                    RenderBudget,
                    "apply_filter",
                    autospec=True,
                    side_effect=RenderBudget.apply_filter,
                ) as apply_filter,
                patch("weblate.utils.render_policy.preflight"),
                self.assertRaises(TemplateSyntaxError),
            ):
                render_template(source, **values)
            # The operation threshold reaches the filter inside the condition,
            # rather than rejecting the surrounding loop or variable lookup.
            apply_filter.assert_called()
        self.assertEqual(
            render_bounded(source, validate_context(values)), "yesyessuffix"
        )

    def test_deadline_inside_condition_is_not_swallowed(self) -> None:
        original = RenderBudget.scalar_size

        def expire(budget: RenderBudget, value: object) -> int:
            # Input is looked up at runtime; expire during comparison accounting.
            budget.deadline = 0
            return original(budget, value)

        source = "{% if value == other %}{% else %}{% endif %}"
        with (
            patch.object(RenderBudget, "scalar_size", expire),
            self.assertRaisesMessage(TemplateSyntaxError, "time limit"),
        ):
            render_bounded(source, {"value": "a", "other": "a"})
        self.assertEqual(render_bounded(source, {"value": "a", "other": "a"}), "")

    @patch("weblate.utils.render_policy.OPERATION_LIMIT", 100000)
    def test_loop_budgets_and_output_limits(self) -> None:
        source = "{% for item in items %}{% endfor %}"
        with self.assertRaisesMessage(TemplateSyntaxError, "loop limit"):
            render_bounded(source, {"items": [0] * (LOOP_LIMIT + 1)})
        for source in (
            "{% for item in items %}{% endfor %}{% for item in items %}{% endfor %}",
            "{% for item in items %}{% for inner in pair %}{% endfor %}{% endfor %}",
        ):
            with (
                self.subTest(source=source),
                self.assertRaisesMessage(TemplateSyntaxError, "loop limit"),
            ):
                render_bounded(
                    source, {"items": [0] * (LOOP_LIMIT // 2 + 1), "pair": [1, 2]}
                )
        source = "{% for item in items %}{{ text }}{% endfor %}"
        context = {"items": [1, 2], "text": "a" * (OUTPUT_LIMIT // 2 + 1)}
        with self.assertRaises(TemplateSyntaxError):
            render_template(source, **context)
        with self.assertRaises(TemplateSyntaxError):
            render_bounded(
                "{% for item in items %}{{ item|lower }}{% endfor %}",
                {"items": ["x"] * 1025},
            )

    def test_resource_error_in_condition_is_sticky(self) -> None:
        source = '{% if value|ljust:"1048577" %}{% else %}{% endif %}'
        with self.assertRaises(TemplateSyntaxError):
            render_template(source, value="text")

    def test_unpacking_error(self) -> None:
        for items in ([[1]], [123], [[1, 2, 3]]):
            with self.subTest(items=items), self.assertRaises(TemplateSyntaxError):
                render_template(
                    "{% for a,b in items %}{{ a }}={{ b }}{% endfor %}", items=items
                )

    @patch("weblate.utils.render_engine.monotonic", new=lambda: 1.0)
    def test_budgets_are_local_to_each_render(self) -> None:
        source = "{% for item in items %}{% if item %}{{ item }}{% endif %}{% endfor %}"
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(
                executor.map(
                    lambda i: render_bounded(source, {"items": [i]}), range(20)
                )
            )
        self.assertEqual(results, [str(i) if i else "" for i in range(20)])
        with self.assertRaises(TemplateSyntaxError):
            render_bounded("{{ value|pprint }}", {"value": "text"})
        self.assertEqual(render_bounded(source, {"items": ["next"]}), "next")

    def test_quoted_delimiters_and_comments_match_django(self) -> None:
        for source in (
            '{{ "{{" }}',
            '{{ "{%" }}',
            '{{ "{#" }}',
            "{# {{ ignored }} {% ignored %} #}ok",
            '{{ value|default:"{{" }}',
            '{% replace value "{{" "{%" %}',
            '{{ "' + "|" * 1100 + '" }}',
        ):
            with self.subTest(source=source):
                self.assert_matches(source, {"value": "{{"})

    def test_condition_terms_respect_quoted_operands(self) -> None:
        phrase = " ".join(["word"] * 65)
        for source in (
            '{% if value == "' + phrase + '" %}yes{% else %}no{% endif %}',
            "{% if value == '" + phrase + "' %}yes{% else %}no{% endif %}",
            '{% if False %}no{% elif value == "' + phrase + '" %}yes{% endif %}',
            '{% if empty|default:"' + phrase + '" %}yes{% endif %}',
        ):
            with self.subTest(source=source[:50]):
                self.assert_matches(source, {"value": phrase, "empty": ""})

    def test_multiline_error_locations(self) -> None:
        for source, line, operation, reason in (
            (
                "heading\n{{ value|center:1048577 }}",
                2,
                'Filter "center"',
                "Intermediate value",
            ),
            (
                "heading\n{% for item in items %}\n{{ value|center:1048577 }}\n{% endfor %}",
                3,
                'Filter "center"',
                "Intermediate value",
            ),
            (
                "{% if False %}no\n{% elif value|center:1048577 %}yes\n{% endif %}",
                2,
                'Filter "center"',
                "Intermediate value",
            ),
            (
                "{% if False %}no\n{% elif value is other %}yes\n{% endif %}",
                2,
                'Tag "elif"',
                "Identity comparisons",
            ),
            (
                "{% if False %}no\n{% elif value in items %}yes\n{% endif %}",
                2,
                'Tag "elif"',
                "condition operator",
            ),
            (
                "heading\n{% replace value 'x' replacement %}",
                2,
                'Tag "replace"',
                "requires string",
            ),
        ):
            with self.subTest(source=source):
                with self.assertRaises(TemplateSyntaxError) as caught:
                    render_template(
                        source,
                        value="private input",
                        other="other",
                        replacement=1,
                        items=[1],
                    )
                message = str(caught.exception)
                self.assertTrue(
                    message.startswith(f"Line {line}: {operation}: "), message
                )
                self.assertIn(reason, message)
                self.assertEqual(message.count("Line "), 1)
                self.assertNotIn("private input", message)
        self.assertEqual(render_template("{{ value|upper }}", value="ok"), "OK")

    def test_parsing_diagnostics(self) -> None:
        for source, reason in (
            ("heading\n{{ value", "Unclosed template token"),
            ("heading\n{{ value\n }}", "cannot span multiple lines"),
            ('heading\n{{ "' + "x" * 2049 + '" }}', "size limit of 2048 bytes"),
            ("heading\n{% include 'file' %}", "Unsupported template tag"),
            ("heading\n{% if True %}", 'Unclosed template tag "if"'),
            ("heading\n{{ value|missing }}", "Invalid filter"),
        ):
            with self.subTest(reason=reason):
                with self.assertRaises(TemplateSyntaxError) as caught:
                    render_template(source, value="text")
                self.assertTrue(str(caught.exception).startswith("Line 2: "))
                self.assertIn(reason, str(caught.exception))
        with (
            patch("weblate.utils.render_policy.PARSE_WORK_LIMIT", 1),
            self.assertRaisesMessage(
                TemplateSyntaxError,
                "Line 2: Template exceeds the parsing work limit of 1 units.",
            ),
        ):
            render_template("heading\n{{ value }}", value="text")
