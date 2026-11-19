# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ast
import json
from datetime import UTC, date, datetime, time
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.template import TemplateSyntaxError
from django.test import SimpleTestCase
from django.utils.html import conditional_escape
from django.utils.timezone import override as override_timezone
from django.utils.translation import override

from weblate.trans import defaults
from weblate.trans.models import Category, Component, Project
from weblate.utils.render import (
    render_repository_template,
    render_template,
    validate_render,
    validate_render_mock,
)
from weblate.utils.render_context import validate_context
from weblate.utils.render_engine import render_bounded
from weblate.utils.render_limits import (
    CONTEXT_LIMIT,
    LOOP_LIMIT,
    OUTPUT_LIMIT,
    SOURCE_LIMIT,
)
from weblate.utils.tests.render_reference import render_reference
from weblate.vcs.base import RepositoryTemplateError


class RenderTest(SimpleTestCase):
    def test_repository_template_failure(self) -> None:
        for template in ("{% invalid %}", "x" * (SOURCE_LIMIT + 1)):
            with self.subTest(template=template[:30]):
                with self.assertRaises(RepositoryTemplateError) as raised:
                    render_repository_template(template, setting="commit message")
                self.assertIsInstance(raised.exception.__cause__, TemplateSyntaxError)
                self.assertIn("commit message", str(raised.exception))
                self.assertEqual(
                    raised.exception.get_stored_error()["code"],
                    "template_render_failed",
                )

    def test_repository_template_unexpected_failure(self) -> None:
        with (
            patch(
                "weblate.utils.render.render_template", side_effect=RuntimeError("bug")
            ),
            self.assertRaisesMessage(RuntimeError, "bug"),
        ):
            render_repository_template("message", setting="commit message")

    def test_validation_shows_source_details_omitted_from_runtime_errors(self) -> None:
        for source, detail, reason in (
            ("{% /private/tree %}", "/private/tree", "Unsupported template tag"),
            (
                '{{ "https://user:dummy@example.invalid/" ? }}',
                "https://user:dummy@example.invalid/",  # kingfisher:ignore
                "Invalid template syntax",
            ),
            ("{{ value|private_filter }}", "private_filter", "Invalid filter"),
            (
                "{{ private_variable }}",
                "private_variable",
                "Undefined template variable",
            ),
        ):
            with self.subTest(reason=reason):
                template = f"heading\n{source}"
                with self.assertRaisesMessage(ValidationError, detail) as validation:
                    validate_render(template)
                self.assertIn("Line 2:", str(validation.exception))
                with self.assertRaises(RepositoryTemplateError) as raised:
                    render_repository_template(template, setting="commit message")
                diagnostic = raised.exception.get_stored_error()["params"]["error"]
                self.assertIn(f"Line 2: {reason}", diagnostic)
                self.assertNotIn(detail, diagnostic)

    def test_unclassified_template_error_omits_raw_diagnostic(self) -> None:
        error = TemplateSyntaxError("Private backend diagnostic")
        with (
            patch("weblate.utils.render.render_template", side_effect=error),
            self.assertRaises(RepositoryTemplateError) as raised,
        ):
            render_repository_template("message", setting="commit message")
        self.assertIn("Template rendering failed", str(raised.exception))
        self.assertNotIn(str(error), str(raised.exception))
        self.assertIs(raised.exception.__cause__, error)

    def test_repository_template_stores_english_diagnostic(self) -> None:
        with (
            override("cs"),
            self.assertRaisesMessage(
                RepositoryTemplateError, "Template value exceeds its size limit."
            ),
        ):
            render_repository_template(
                "x" * (SOURCE_LIMIT + 1), setting="commit message"
            )

    def test_component_full_name(self) -> None:
        project = Project(name="Project", slug="project")
        component = Component(
            name="Component", slug="component", project=project, source_language_id=1
        )
        parent = None
        for depth in range(4):
            if depth:
                parent = Category(
                    name=f"Category {depth}",
                    slug=f"category-{depth}",
                    project=project,
                    category=parent,
                )
            component.category = parent
            expected = "/".join(
                [
                    project.name,
                    *(f"Category {index}" for index in range(1, depth + 1)),
                    component.name,
                ]
            )
            with (
                self.subTest(depth=depth),
                patch.object(Component, "repository") as repository,
            ):
                repository.get_remote_branch_name.return_value = "main"
                self.assertEqual(
                    render_template(
                        "{{ component_full_name }}|{{ project_name }}|{{ component_name }}",
                        component=component,
                    ),
                    f"{expected}|Project|Component",
                )
                for message in (
                    defaults.DEFAULT_COMMIT_MESSAGE,
                    defaults.DEFAULT_ADD_MESSAGE,
                    defaults.DEFAULT_DELETE_MESSAGE,
                    defaults.DEFAULT_MERGE_MESSAGE,
                    defaults.DEFAULT_ADDON_MESSAGE,
                    defaults.DEFAULT_PULL_MESSAGE,
                ):
                    rendered = render_template(
                        message,
                        component=component,
                        language_name="Czech",
                        stats={"translated_percent": 100, "translated": 1, "all": 1},
                        addon_name="Test add-on",
                        component_linked_children=[],
                    )
                    self.assertIn(expected, rendered)

    def test_linked_component_full_name(self) -> None:
        project = Project(name="Project", slug="project")
        category = Category(name="Category", slug="category", project=project)
        component = Component(
            name="Component", slug="component", project=project, source_language_id=1
        )
        linked = Component(
            name="Linked",
            slug="linked",
            project=project,
            category=category,
            source_language_id=1,
        )
        component.__dict__["linked_children"] = [linked]
        children = component.get_linked_children_for_template()
        self.assertEqual(children[0]["name"], "Linked")
        self.assertEqual(children[0]["project_name"], "Project")
        self.assertEqual(children[0]["full_name"], "Project/Category/Linked")
        with patch.object(Component, "repository") as repository:
            repository.get_remote_branch_name.return_value = "main"
            rendered = render_template(
                defaults.DEFAULT_PULL_MESSAGE,
                component=component,
                component_linked_children=children,
            )
        self.assertIn("[Project/Category/Linked]", rendered)

    def test_full_name_template_validation(self) -> None:
        for template in ("{{ component_full_name }}", defaults.DEFAULT_PULL_MESSAGE):
            with patch.object(
                Component, "get_linked_children_for_template", return_value=[]
            ):
                self.assertIn("project/component", validate_render_mock(template))

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

    def test_simple_substitutions(self) -> None:
        self.assertEqual(
            render_template(
                "{{ branch }}/{{ filename }}:{{ line }}",
                branch="main",
                filename="cs.po",
                line=9,
            ),
            "main/cs.po:9",
        )

    def test_plain_text_does_not_compile(self) -> None:
        with patch(
            "weblate.utils.render_engine.RestrictedTemplate"
        ) as compile_template:
            self.assertEqual(render_bounded("plain text", {}), "plain text")
        compile_template.assert_not_called()

    def test_bounded_filter_compatibility(self) -> None:
        expressions = (
            "value|parentdir|parentdir",
            "value|dirname",
            "value|stripext",
            "value|lower",
            "value|upper",
            "value|capfirst",
            "value|title",
            "value|urlencode",
            'value|urlencode:""',
            "value|iriencode",
            'value|cut:"a"',
            'value|slice:"::-1"',
            "value|length",
            "value|first",
            "value|last",
            'value|default:"fallback"',
            'value|default_if_none:"fallback"',
            'value|yesno:"yes,no,maybe"',
            "value|yesno",
            "value|escape",
            "value|force_escape",
            "value|escapejs",
            "value|addslashes",
            "value|escape|escape",
            "value|escape|force_escape",
            "value|escape|upper|escape",
            "value|cut:options.remove|slice:options.range",
            '"<b>literal</b>"|escape',
            "value|length|default:7",
            "stats.translated|default:stats.all",
            'value | upper | cut:"A"',
            "'a\\'b|c:d'|addslashes",
        )
        for value in ("", "a/b/file.po", "Český ß ﬃ İ <b>&\"'\\\n\u2028"):
            values: dict[str, object] = {
                "value": value,
                "options": {"remove": "a", "range": "1:4"},
                "stats": {"translated": 0, "all": 7},
            }
            for expression in expressions:
                source = "prefix {{ " + expression + " }} suffix"
                with self.subTest(value=value, expression=expression), override("en"):
                    expected = render_reference(source, validate_context(values))
                    self.assertEqual(render_template(source, **values), expected)

    def test_bounded_scalar_defaults(self) -> None:
        for value in (None, True, False, 0, 12, 1.25, ""):
            for expression in (
                'value|default:"<b>fallback</b>"',
                'value|default_if_none:"fallback"',
                'value|yesno:"yes,no,maybe"',
                "value|default:False",
                "value|default_if_none:None",
            ):
                source = "{{ " + expression + " }}"
                with self.subTest(value=value, expression=expression), override("en"):
                    self.assertEqual(
                        render_template(source, value=value),
                        render_reference(source, {"value": value}),
                    )

    def test_bounded_hot_paths(self) -> None:
        source = (
            "https://github.com/godotengine/godot-docs/blob/master/"
            "{{filename|parentdir|parentdir|parentdir}}#L{{line}}"
        )
        with patch.object(Component, "repository") as repository:
            repository.get_remote_branch_name.return_value = "main"
            self.assertEqual(
                render_template(
                    source,
                    filename="../../docs/tutorials/3d/3d_antialiasing.rst",
                    line="341",
                ),
                "https://github.com/godotengine/godot-docs/blob/master/"
                "tutorials/3d/3d_antialiasing.rst#L341",
            )
            for message in (
                defaults.DEFAULT_COMMIT_MESSAGE,
                defaults.DEFAULT_ADD_MESSAGE,
                defaults.DEFAULT_DELETE_MESSAGE,
                defaults.DEFAULT_MERGE_MESSAGE,
                defaults.DEFAULT_ADDON_MESSAGE,
            ):
                self.assertIn(
                    "project/component",
                    validate_render_mock(
                        message,
                        language_name="Czech",
                        addon_name="addon",
                        stats={"translated_percent": 100, "translated": 1, "all": 1},
                    ),
                )

    def test_bounded_dictionary_lookups(self) -> None:
        values: dict[str, object] = {
            "stats": {"items": "item", "get": "getter", "nested": {"0": 3}}
        }
        for expression in ("stats.items", "stats.get", "stats.nested.0"):
            source = "{{ " + expression + " }}"
            with self.subTest(expression=expression):
                self.assertEqual(
                    render_template(source, **values),
                    render_reference(source, validate_context(values)),
                )

    def test_unsupported_operands_fail_directly(self) -> None:
        for source, values in (
            ("{{ value.items }}", {"value": {}}),
            ("{{ value|cut:123 }}", {"value": "text"}),
        ):
            with self.subTest(source=source), self.assertRaises(TemplateSyntaxError):
                render_template(source, **values)

    def test_bounded_validates_before_transforming(self) -> None:
        with (
            patch("weblate.utils.render_engine.RenderBudget.apply_filter") as apply,
            self.assertRaises(TemplateSyntaxError),
        ):
            render_bounded("{{ value|upper }}{{ value|pprint }}", {"value": "text"})
        apply.assert_not_called()

    def test_bounded_budgets_fail_directly(self) -> None:
        for limit, source, values in (
            ("FILTER_LIMIT", "{{ value|upper|lower }}", {"value": "text"}),
            ("WORK_LIMIT", "{{ value|upper }}", {"value": "text"}),
            ("OPERATION_LIMIT", "{{ stats.translated }}", {"stats": {"translated": 1}}),
        ):
            with (
                self.subTest(limit=limit),
                patch("weblate.utils.render_policy." + limit, 1),
                self.assertRaises(TemplateSyntaxError),
            ):
                render_bounded(source, validate_context(dict(values)))
        with self.assertRaises(TemplateSyntaxError):
            render_bounded(
                "{{ value|upper }}", {"value": "a" * (OUTPUT_LIMIT // 3 + 1)}
            )
        with self.assertRaises(TemplateSyntaxError):
            render_bounded("{{ value|upper }}", {"value": "a" * (OUTPUT_LIMIT + 1)})

    def test_bounded_escaping_returns_plain_text(self) -> None:
        rendered = render_template("{{ value|escape }}", value="<b>text</b>")
        self.assertIs(type(rendered), str)
        self.assertEqual(rendered, "&lt;b&gt;text&lt;/b&gt;")

    def test_unknown_variables_and_tags(self) -> None:
        for source in ("{{ missing }}", "{% include 'file' %}", "{% load static %}"):
            with self.subTest(source=source), self.assertRaises(TemplateSyntaxError):
                render_template(source)

    @patch("weblate.utils.render_policy.OPERATION_LIMIT", 100000)
    def test_loop_limit(self) -> None:
        template = "{% for value in values %}x{% endfor %}"
        self.assertEqual(
            render_template(template, values=[0] * LOOP_LIMIT), "x" * LOOP_LIMIT
        )
        with self.assertRaisesMessage(TemplateSyntaxError, "loop limit"):
            render_template(template, values=[0] * (LOOP_LIMIT + 1))

    def test_output_byte_limit(self) -> None:
        value = "é" * (OUTPUT_LIMIT // 2)
        for template in ("{{ value }}", "{% if True %}{{ value }}{% endif %}"):
            with self.subTest(template=template):
                self.assertEqual(render_template(template, value=value), value)
                with self.assertRaises(TemplateSyntaxError):
                    render_template(template, value=value + "é")
                with self.assertRaises(TemplateSyntaxError):
                    render_template(template + "x", value=value)

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

    def test_deadline_fails_and_resets(self) -> None:
        with (
            patch("weblate.utils.render_engine.RENDER_TIMEOUT", -1),
            self.assertRaisesMessage(TemplateSyntaxError, "time limit"),
        ):
            render_template("{{ value|upper }}", value="text")
        self.assertEqual(render_template("{{ value|upper }}", value="text"), "TEXT")

    def test_current_timezone(self) -> None:
        with override_timezone("Europe/Prague"):
            self.assertEqual(
                render_template(
                    '{{ value|date:"H:i" }}', value=datetime(2026, 1, 1, tzinfo=UTC)
                ),
                "01:00",
            )
