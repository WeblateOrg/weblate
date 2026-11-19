# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import UTC, date, time
from decimal import Decimal
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.template import TemplateSyntaxError
from django.test import SimpleTestCase

from weblate.utils.render import (
    prepare_template_context,
    render_template,
    validate_render,
)
from weblate.utils.render_engine import RenderBudget, get_engine
from weblate.utils.render_filters import FILTERS
from weblate.utils.tests.render_reference import render_reference


class TemplateFiltersTest(SimpleTestCase):
    def test_supported_filters_match_django(self) -> None:
        cases: tuple[tuple[str, object], ...] = (
            ("linenumbers", "a\nb\n"),
            ("make_list|join:':'", "Český"),
            ("slugify", "Český <b>name</b>"),
            ("slugify", "Český" * 1000),
            ("truncatechars:6", "a long sentence"),
            ("truncatewords:2", "a long sentence"),
            ("wordcount", "a long sentence"),
            ("wordwrap:6", "a long sentence"),
            ("linebreaks", "a\nb\n\nc"),
            ("linebreaksbr", "a\nb\n"),
            ("safe|escape", "<b>name</b>"),
            ("phone2numeric", "1-800-WEBLATE"),
            ("random", ["only"]),
            ("safeseq|join:','|escape", ["<b>", "&"]),
            ("escapeseq|join:','", ["<b>", "&"]),
            ("add:3", 2),
            ("add:'cd'", "ab"),
            ("add:other|json", [1, 2]),
            ("get_digit:2", 123),
            ("divisibleby:3", 123),
            ("filesizeformat", 12345),
            ("pluralize:'y,ies'", 2),
            ("pluralize", []),
            ("center:10", "Český"),
            ("ljust:10", "a"),
            ("rjust:10", "a"),
            ("floatformat:'2g'", Decimal("1234.567")),
            ("floatformat:'-2u'", 1.25),
            ("stringformat:'08x'", 123),
            ("stringformat:'.2f'", 1.25),
            ("stringformat:'10s'", "text"),
            ("date:'Y-m-d'", date(2026, 1, 2)),
            ("time:'H:i'", date(2026, 1, 2)),
            ("timesince:then", date(2026, 1, 2)),
            ("timeuntil:then", date(2026, 1, 2)),
        )
        for expression, value in cases:
            source = "{{ value|" + expression + " }}"
            values: dict[str, object] = {
                "value": value,
                "other": [3],
                "then": date(2026, 1, 5),
            }
            with self.subTest(expression=expression):
                expected = render_reference(
                    source, prepare_template_context(source, values)
                )
                self.assertEqual(render_template(source, **values), expected)

    def test_registered_filters_have_handlers(self) -> None:
        exposed = {
            name
            for library in get_engine().template_builtins
            for name in library.filters
        }
        self.assertEqual(exposed, set(FILTERS))

    def test_excluded_filters_are_rejected_even_in_dead_branches(self) -> None:
        for name in (
            "urlize",
            "urlizetrunc",
            "striptags",
            "truncatechars_html",
            "truncatewords_html",
            "dictsort",
            "dictsortreversed",
            "unordered_list",
            "pprint",
            "json_script",
        ):
            source = "{% if False %}{{ value|" + name + " }}{% endif %}"
            with (
                self.subTest(name=name),
                self.assertRaisesMessage(TemplateSyntaxError, "Invalid filter"),
            ):
                render_template(source, value="text")

    def test_allocations_are_rejected_before_calling_native_filter(self) -> None:
        for name, value, args in (
            ("center", "a", (1000000000,)),
            ("ljust", "a", (1000000000,)),
            ("rjust", "a", (1000000000,)),
            ("floatformat", 1.5, (1000000000,)),
            ("floatformat", 1.5, (Decimal("1E+999999999"),)),
            ("floatformat", 1.5, (1e100,)),
            ("stringformat", "a", ("1000000000s",)),
            ("stringformat", 1.5, (".1000000000f",)),
            ("stringformat", Decimal("1E+999999999"), ("d",)),
            ("add", Decimal("1E+999999999"), (1,)),
            ("make_list", "a" * 40000, ()),
            ("add", [None] * 20000, ([None] * 20000,)),
            ("slugify", "\u0315\u0300" * 3000, ()),
            ("truncatechars", "\u0315\u0300" * 3000, (10,)),
            ("date", date(2026, 1, 2), ("r" * 10000,)),
        ):
            function = Mock()
            with self.subTest(name=name), self.assertRaises(TemplateSyntaxError):
                RenderBudget().apply_filter(name, function, value, args, {})
            function.assert_not_called()

    def test_chained_expansion_and_large_loop_bodies(self) -> None:
        sources = (
            "{{ value" + "|json" * 25 + " }}",
            "{{ value" + "|escapejs" * 25 + " }}",
            "{% replace value '' value as value %}" * 25,
            "{% for item in items %}" + "{{ value|lower }}" * 200 + "{% endfor %}",
        )
        for source in sources:
            with (
                self.subTest(source=source[:60]),
                self.assertRaises(TemplateSyntaxError),
            ):
                render_template(source, value="\\" * 1024, items=[0] * 100)
        self.assertEqual(render_template("{{ value|upper }}", value="ok"), "OK")

    def test_original_nested_loop_attack(self) -> None:
        source = "{% for c in widget_url %}" * 6 + "{% endfor %}" * 6
        with self.assertRaises(TemplateSyntaxError):
            render_template(
                source,
                widget_url="http://example.com/widget/project/component/matrix-auto.svg",
            )

    def test_formatting_work_counts_without_output(self) -> None:
        source = (
            "{% for item in items %}{% if value|center:1000 %}{% endif %}{% endfor %}"
        )
        with (
            patch("weblate.utils.render_policy.WORK_LIMIT", 10000),
            self.assertRaises(TemplateSyntaxError),
        ):
            render_template(source, value="a", items=[0] * 100)

    def test_invalid_values_report_template_errors(self) -> None:
        for source, value in (
            ("{{ value }}", Decimal("NaN")),
            ('{{ value|floatformat:"" }}', 1.5),
        ):
            with self.subTest(source=source), self.assertRaises(TemplateSyntaxError):
                render_template(source, value=value)

    def test_ordinary_filter_errors_in_conditions_match_django(self) -> None:
        for expression, value in (
            ("value|divisibleby:0", 2),
            ('value|center:"bad"', 2),
            ('value|floatformat:""', 2),
            ("value|json", time(1, 2, tzinfo=UTC)),
            ("value|python", time(1, 2, tzinfo=UTC)),
        ):
            for condition in (
                "not " + expression,
                expression + " or True",
                expression + " == True",
            ):
                source = "{% if " + condition + " %}yes{% else %}no{% endif %}"
                with self.subTest(condition=condition):
                    self.assertEqual(
                        render_template(source, value=value),
                        render_reference(source, {"value": value}),
                    )

    def test_text_stringformat_preserves_bounded_long_values(self) -> None:
        for conversion in ("s", "r", "a"):
            value = "Český" * 1000
            source = '{{ value|stringformat:"' + conversion + '" }}'
            with self.subTest(conversion=conversion):
                self.assertEqual(
                    render_template(source, value=value),
                    render_reference(source, {"value": value}),
                )

    def test_wordwrap_checks_tab_expansion_before_allocating(self) -> None:
        function = Mock()
        with self.assertRaises(TemplateSyntaxError):
            RenderBudget().apply_filter(
                "wordwrap", function, "\t" * 140000 + "a", (2000000,), {}
            )
        function.assert_not_called()
        source = "{{ value|wordwrap:10000 }}"
        value = "\t" * 1000 + "a"
        self.assertEqual(
            render_template(source, value=value),
            render_reference(source, {"value": value}),
        )

    def test_add_long_text_preserves_django_behavior(self) -> None:
        source = "{{ value|add:other }}"
        for value, other in (
            ("a" * 1241, "suffix"),
            ("prefix", "Český" * 1000),
            ("1" * 2000, "suffix"),
            ("12", "34"),
            ("  +1_2 ", "٣٤"),
            ("1__" * 500, "2"),
            ("\x1c" + "1" * 1241, "2"),
        ):
            with self.subTest(value=value[:10], other=other[:10]):
                self.assertEqual(
                    render_template(source, value=value, other=other),
                    render_reference(source, {"value": value, "other": other}),
                )

    def test_add_long_text_checks_allocation_and_numeric_conversion(self) -> None:
        for value, other in (
            ("a" * 600000, "b" * 600000),
            ("1" * 1241, "2"),
            ("1_" * 1241 + "1", "2"),
            ("  +" + "١" * 1241 + " ", "2"),
        ):
            function = Mock()
            with self.subTest(value=value[:10]), self.assertRaises(TemplateSyntaxError):
                RenderBudget().apply_filter("add", function, value, (other,), {})
            function.assert_not_called()

    def test_container_value_filters_match_django(self) -> None:
        for value in ([], [1], {}, {"a": 1}):
            for expression in (
                "value|yesno",
                "value|yesno:'present,empty,unknown'",
                "value|default:fallback|json",
                "value|default_if_none:fallback|json",
                "none|default_if_none:value|json",
                "value|default:fallback|length",
            ):
                source = "{{ " + expression + " }}"
                values: dict[str, object] = {
                    "value": value,
                    "fallback": ["fallback"],
                    "none": None,
                }
                with self.subTest(value=value, expression=expression):
                    self.assertEqual(
                        render_template(source, **values),
                        render_reference(source, values),
                    )
        for source in (
            "{% for item in value|default:fallback %}{{ item }}{% endfor %}",
            "{{ data.items|yesno }}",
            "{{ data.keys|default:fallback|join:',' }}",
            "{{ data.values|default_if_none:fallback|length }}",
        ):
            values = {"value": [], "fallback": ["fallback"], "data": {"a": "b"}}
            with self.subTest(source=source):
                self.assertEqual(
                    render_template(source, **values), render_reference(source, values)
                )
        with self.assertRaises(TemplateSyntaxError):
            render_template("{{ value|default:fallback }}", value=[], fallback=[1])

    def test_filter_diagnostics(self) -> None:
        for source, value, message in (
            (
                '{{ value|center:"1048577" }}',
                "private input",
                'Filter "center": Intermediate value would exceed the size limit of 1048576 bytes.',
            ),
            (
                "{{ value|cut:123 }}",
                "private input",
                'Filter "cut": This filter requires strings.',
            ),
            (
                "{{ value|floatformat:1001 }}",
                1.5,
                'Filter "floatformat": Formatting precision exceeds the limit of 1000 places.',
            ),
        ):
            with self.subTest(source=source):
                with self.assertRaises(TemplateSyntaxError) as caught:
                    render_template(source, value=value)
                self.assertEqual(str(caught.exception), message)

    def test_work_diagnostic_identifies_filter(self) -> None:
        source = "{% for item in items %}{% if value|lower %}{% endif %}{% endfor %}"
        with (
            patch("weblate.utils.render_policy.WORK_LIMIT", 1000),
            self.assertRaisesMessage(
                TemplateSyntaxError,
                'Filter "lower": Template exceeds the cumulative work limit of 1000 bytes.',
            ),
        ):
            render_template(source, value="private input" * 10, items=[0] * 10)

    def test_native_filter_error_omits_context_values(self) -> None:
        source = "{{ text|center:width }}"
        with self.assertRaises(TemplateSyntaxError) as caught:
            render_template(source, text="example", width="private input")
        self.assertEqual(
            str(caught.exception),
            'Filter "center": Value or argument has an invalid format.',
        )
        with self.assertRaisesMessage(
            ValidationError, str(caught.exception)
        ) as validation:
            validate_render(source, text="example", width="private input")
        self.assertNotIn("private input", str(validation.exception))
