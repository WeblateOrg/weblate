# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Never
from unittest.mock import patch
from uuid import UUID

from django.core.exceptions import ValidationError
from django.template import TemplateSyntaxError
from django.test import SimpleTestCase
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy

from weblate.utils.render import render_template, validate_render
from weblate.utils.render_context import ContextSnapshot, validate_context
from weblate.utils.render_engine import render_bounded
from weblate.utils.render_limits import CONTEXT_LIMIT, DEPTH_LIMIT
from weblate.utils.tests.render_reference import render_reference


class TemplateContextTest(SimpleTestCase):
    def test_supported_values(self) -> None:
        now = datetime(2026, 1, 2, 3, 4, tzinfo=timezone(timedelta(hours=2)))
        values = {
            "text": "Český <b>text</b>",
            "int": 123,
            "float": 1.25,
            "bool": True,
            "none": None,
            "date": date(2026, 1, 2),
            "time": time(3, 4),
            "datetime": now,
            "decimal": Decimal("1.25"),
            "uuid": UUID("12345678-1234-5678-1234-567812345678"),
            "tuple": ("text", 1),
            "list": [False, {"nested": None}],
        }
        context = validate_context(values)
        expected = {**values, "uuid": str(values["uuid"]), "tuple": ["text", 1]}
        self.assertEqual(context, expected)
        for key in context:
            source = "{{ " + key + "|json }}"
            with self.subTest(key=key):
                self.assertEqual(
                    render_template(source, **values), render_reference(source, context)
                )

    def test_snapshot_owns_containers(self) -> None:
        shared = {"items": ["original"]}
        values = {"first": shared, "second": shared}
        snapshot = validate_context(dict(values))
        shared["items"].append("changed")
        values["first"] = {"other": []}
        self.assertEqual(
            snapshot,
            {"first": {"items": ["original"]}, "second": {"items": ["original"]}},
        )
        self.assertIsNot(snapshot["first"], snapshot["second"])

    def test_normalized_values(self) -> None:
        context = validate_context({"uuid": UUID(int=0), "values": ("a", "b")})
        source = "{{ uuid|upper }}"
        self.assertEqual(
            render_bounded(source, context), render_reference(source, context)
        )
        self.assertEqual(render_template("{{ values|join:',' }}", **context), "a,b")

    def test_unsupported_unused_values_fail_before_evaluation(self) -> None:
        class String(str):  # ruff: ignore[subclass-builtin]
            __slots__ = ()

        class Integer(int):
            pass

        class Dictionary(dict):  # ruff: ignore[subclass-builtin]
            pass

        class List(list):  # ruff: ignore[subclass-builtin]
            pass

        class Tuple(tuple):
            __slots__ = ()

        class DateTime(datetime):
            pass

        class Number(Decimal):
            pass

        for invalid in (
            object(),
            gettext_lazy("Delete"),
            mark_safe("<b>safe</b>"),
            String("text"),
            Integer(1),
            Dictionary(),
            List(),
            Tuple(),
            DateTime(2026, 1, 1),
            Number("1"),
            float("nan"),
            float("inf"),
            float("-inf"),
            {1: "not a string key"},
            {String("key"): "value"},
        ):
            with (
                self.subTest(value_type=type(invalid)),
                self.assertRaises(TemplateSyntaxError),
            ):
                render_template("plain", unused=[{"nested": invalid}])

        with (
            patch("weblate.utils.render.render_bounded") as render,
            self.assertRaises(TemplateSyntaxError),
        ):
            render_template("{{ value|upper }}", value="text", unused=object())
        render.assert_not_called()

    def test_invalid_context_is_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            validate_render("plain", unused=object())

    def test_rejection_does_not_consult_object_hooks(self) -> None:
        class Hooks:
            def __getattribute__(self, name: str) -> Never:
                msg = "Unexpected attribute access"
                raise AssertionError(msg)

            def __str__(self) -> str:
                msg = "Unexpected string conversion"
                raise AssertionError(msg)

            def __getattr__(self, name: str) -> Never:
                msg = "Unexpected attribute lookup"
                raise AssertionError(msg)

            def __eq__(self, other: object) -> Never:
                msg = "Unexpected comparison"
                raise AssertionError(msg)

            def __hash__(self) -> int:
                return hash("text")

        class List(list):  # ruff: ignore[subclass-builtin]
            # This hook must fail if validation attempts to iterate a subclass.
            def __iter__(self) -> Never:  # pylint: disable=non-iterator-returned
                msg = "Unexpected iteration"
                raise AssertionError(msg)

        class Dictionary(dict):  # ruff: ignore[subclass-builtin]
            def items(self) -> Never:
                msg = "Unexpected dictionary iteration"
                raise AssertionError(msg)

            def __getitem__(self, key: str) -> Never:
                msg = "Unexpected dictionary lookup"
                raise AssertionError(msg)

        for field in ("translation", "component", "project", "unused"):
            for value in (Hooks(), List(), Dictionary(), {Hooks(): "text"}):
                with self.subTest(field=field), self.assertRaises(TemplateSyntaxError):
                    render_template("plain", **{field: value})

    def test_context_limits_apply_to_plain_text(self) -> None:
        nested: object = "text"
        for _index in range(DEPTH_LIMIT + 1):
            nested = [nested]
        cycle: list[object] = []
        cycle.append(cycle)
        shared: object = "text"
        for _index in range(20):
            shared = [shared, shared]
        for value in (
            nested,
            cycle,
            shared,
            "x" * (CONTEXT_LIMIT + 1),
            1 << (CONTEXT_LIMIT * 4),
        ):
            with (
                self.subTest(value_type=type(value)),
                self.assertRaises(TemplateSyntaxError),
            ):
                render_template("plain", unused=value)

    def test_context_depth_boundary(self) -> None:
        nested: object = "text"
        for _index in range(DEPTH_LIMIT - 1):
            nested = [nested]
        self.assertEqual(render_template("plain", unused=nested), "plain")
        with self.assertRaises(TemplateSyntaxError):
            render_template("plain", unused=[nested])

    def test_invalid_utf8(self) -> None:
        for source, values in (
            ("\ud800", {}),
            ("plain", {"data": "\udfff"}),
            ("plain", {"data": {"\ud800": "text"}}),
        ):
            with self.subTest(source=repr(source), values=repr(values)):
                with self.assertRaisesMessage(TemplateSyntaxError, "UTF-8"):
                    render_template(source, **values)
                with self.assertRaises(ValidationError):
                    validate_render(source, **values)

    def test_decimal_size_before_formatting(self) -> None:
        value = Decimal("1" * 1000)
        with patch("weblate.utils.render_context.CONTEXT_LIMIT", 512):
            snapshot = ContextSnapshot()
        with (
            patch("weblate.utils.render_context.str", create=True) as stringify,
            self.assertRaisesMessage(TemplateSyntaxError, "context exceeds"),
        ):
            snapshot.copy(value)
        stringify.assert_not_called()

    def test_compact_decimal_representations(self) -> None:
        for value in (
            Decimal("1.25"),
            Decimal("0.00000100"),
            Decimal("1E+999999999"),
            Decimal("1E-999999999"),
        ):
            with self.subTest(value=value):
                self.assertEqual(validate_context({"value": value}), {"value": value})
