# Copyright © Henry Wilkes <henry@torproject.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import itertools
import re
from typing import TYPE_CHECKING

from django.test import SimpleTestCase

from weblate.checks.flags import Flags
from weblate.checks.fluent.inner_html import (
    FluentSourceInnerHTMLCheck,
    FluentTargetInnerHTMLCheck,
)
from weblate.checks.fluent.parts import FluentPartsCheck
from weblate.checks.fluent.references import FluentReferencesCheck
from weblate.checks.fluent.syntax import (
    FluentSourceSyntaxCheck,
    FluentTargetSyntaxCheck,
)

if TYPE_CHECKING:
    from weblate.checks.base import Check

from weblate.checks.tests.test_checks import MockUnit


class MockFluentTransUnit(MockUnit):
    def __init__(
        self,
        source: str,
        target: str = "",
        fluent_type: str | None = None,
        unit_id: str = "",
        is_source: bool = False,
    ) -> None:
        self._fluent_type = fluent_type
        flags = Flags()
        if fluent_type:
            flags.set_value("fluent-type", fluent_type)
        flags.merge(
            [
                # Add flags so that should_skip returns False.
                "fluent-source-syntax",
                "fluent-target-syntax",
                "fluent-parts",
                "fluent-references",
                "fluent-source-inner-html",
                "fluent-target-inner-html",
            ]
        )
        super().__init__(
            flags=flags,
            source=source,
            target=target,
            context=unit_id,
            is_source=is_source,
        )

    def __str__(self) -> str:
        fluent_type = self._fluent_type or ""
        source = self.get_source_plurals()[0]
        if self.is_source:
            return f"{fluent_type} ({source!r})"
        target = self.get_target_plurals()[0]
        return f"{fluent_type} ({source!r} -> {target!r})"


class MockCheckModel:  # noqa: B903
    # Mock Check object from weblate.checks.models
    def __init__(self, unit: MockFluentTransUnit) -> None:
        self.unit = unit


class FluentCheckTestBase(SimpleTestCase):
    @staticmethod
    def _create_source_unit(source: str, fluent_type: str) -> MockFluentTransUnit:
        return MockFluentTransUnit(
            source,
            target="",
            fluent_type=fluent_type,
            unit_id=("-test-term" if fluent_type == "Term" else "test-message"),
            is_source=True,
        )

    @staticmethod
    def _create_target_unit(
        source: str, target: str, fluent_type: str
    ) -> MockFluentTransUnit:
        return MockFluentTransUnit(
            source,
            target=target,
            fluent_type=fluent_type,
            unit_id=("-test-term" if fluent_type == "Term" else "test-message"),
            is_source=False,
        )

    def assert_check_description(
        self,
        check: Check,
        unit: MockFluentTransUnit,
        description: str | re.Pattern,
    ) -> None:
        check_desc = check.get_description(MockCheckModel(unit))
        if isinstance(description, str):
            self.assertHTMLEqual(
                check_desc,
                description,
                f"Description HTML for {check.check_id} should match for {unit}",
            )
        else:
            self.assertRegex(
                check_desc,
                description,
                f"Description for {check.check_id} should match regex for {unit}",
            )

    SOURCE_CHECKS = [FluentSourceSyntaxCheck(), FluentSourceInnerHTMLCheck()]
    TARGET_CHECKS = [
        FluentTargetSyntaxCheck(),
        FluentPartsCheck(),
        FluentReferencesCheck(),
        FluentTargetInnerHTMLCheck(),
    ]

    def assert_checks(
        self,
        source: str,
        target: str,
        fluent_type: str,
        check_state: dict[type[Check], bool] | None = None,
    ) -> None:
        if check_state is None:
            check_state = {}
        source_unit = self._create_source_unit(source, fluent_type)
        check: Check
        for check in self.SOURCE_CHECKS:
            if check_state.get(check.__class__, True):
                self.assertFalse(
                    check.check_source_unit([source], source_unit),
                    f"Check {check.check_id} should pass for {source_unit}",
                )
            else:
                self.assertTrue(
                    check.check_source_unit([source], source_unit),
                    f"Check {check.check_id} should fail for {source_unit}",
                )
        target_unit = self._create_target_unit(source, target, fluent_type)
        for check in self.TARGET_CHECKS:
            if check_state.get(check.__class__, True):
                self.assertFalse(
                    check.check_single(source, target, target_unit),
                    f"Check {check.check_id} should pass for {target_unit}",
                )
            else:
                self.assertTrue(
                    check.check_single(source, target, target_unit),
                    f"Check {check.check_id} should fail for {target_unit}",
                )

    def assert_source_check_passes(
        self,
        check: Check,
        source: str,
        fluent_type: str,
    ) -> None:
        unit = self._create_source_unit(source, fluent_type)
        self.assertFalse(
            check.check_source_unit([source], unit),
            f"Check {check.check_id} should pass for {unit}",
        )

    def assert_source_check_fails(
        self,
        check: Check,
        source: str,
        fluent_type: str,
        description: str | re.Pattern,
    ) -> None:
        unit = self._create_source_unit(source, fluent_type)
        self.assertTrue(
            check.check_source_unit([source], unit),
            f"Check {check.check_id} should fail for {unit}",
        )
        self.assert_check_description(check, unit, description)

    def assert_target_check_passes(
        self,
        check: Check,
        source: str,
        target: str,
        fluent_type: str,
    ) -> None:
        unit = self._create_target_unit(source, target, fluent_type)
        self.assertFalse(
            check.check_single(source, target, unit),
            f"Check {check.check_id} should pass for {unit}",
        )

    def assert_target_check_fails(
        self,
        check: Check,
        source: str,
        target: str,
        fluent_type: str,
        description: str | re.Pattern,
    ) -> None:
        unit = self._create_target_unit(source, target, fluent_type)
        self.assertTrue(
            check.check_single(source, target, unit),
            f"Check {check.check_id} should fail for {unit}",
        )
        self.assert_check_description(check, unit, description)

    def assert_source_highlights(
        self,
        check: Check,
        source: str,
        fluent_type: str,
        highlights: list[tuple[int, str]],
    ) -> None:
        unit = self._create_target_unit(source, "", fluent_type)
        self.assertEqual(
            check.check_highlight(source, unit),
            [(start, start + len(string), string) for start, string in highlights],
            f"Highlights for {check.check_id} should match for {unit}",
        )


class FluentSyntaxCheckTestBase:
    """
    Tests we want to run for both source and target syntax checks.

    The fluent syntax checks should act the same on both source and targets, so
    we want to run the same tests.
    """

    def assert_syntax_ok(self, value: str, fluent_type: str) -> None:
        raise NotImplementedError

    def assert_syntax_error(
        self,
        value: str,
        fluent_type: str,
        description: str | re.Pattern,
    ) -> None:
        raise NotImplementedError

    def test_syntax_ok(self) -> None:
        for value in (
            "Test string",
            "Test string!",
            "🍄",
            "A -> B",
            "test [string]",
            "test.string",
            "] test string",
            "test * string",
            "test = string",
            "test <p string",  # Invalid HTML is ok Fluent syntax.
            "with\n  new line",
            "reference a { message }",
            "reference a { message.attr }",
            "reference a { -term }",
            'reference a { -term(tense: "past") }',
            "reference a { $variable }",
            'call a { FUNCTION($n, val1: "hello", val2: -3.5) }',
            '{ "[" } literals { 3 }',
            '{ "with\\"quote and \\\\backslash" } in literal',
            'literal { "with \\u27BDunicode" }',
            'using { "\\u27bdlower case" } hex',
            'longer { "unicode\\U01F700number" }',
            # Invalid unicode escape is ok.
            '{ "my\\UFFFFFFbad unicode" }',
            "{ $var ->\n*[other] ok\n}",
            "{ -term.attr ->\n*[other] ok\n}",  # Term reference ok in selector.
        ):
            for fluent_type in ("Term", "Message"):
                self.assert_syntax_ok(value, fluent_type)
                self.assert_syntax_ok(f"ok\n.attribute={value}", fluent_type)
        # Message with no value is ok
        self.assert_syntax_ok(".attr = ok", "Message")

    def test_syntax_errors(self) -> None:
        # The error message comes from translate, we just look for the prefix
        # and a non-empty error.
        error_message = re.compile(r"^Fluent syntax error: .")
        for value in (
            "open { ref",
            "close } ref",
            "ref { with gap }",
            "ref { -term.attr }",  # Term attribute cannot be referenced.
            "invalid { message@id }",
            "invalid number { .5 } literal",
            'invalid escape { "\\a" } literal',
            'unicode { "\\u123x" } hex character missing',
            'unicode sequence { "\\U0012b" } too short',
            " ",
            "\n",
            "lower case { function($n) }",
            "{ $var ->\n[other] ok\n}",  # Missing default variant.
            "{ $var -> *[other] ok\n}",  # Missing newline.
            "{ $var ->\n*[other] ok }",  # Missing newline.
            "{ message ->\n*[other] ok\n}",  # Message selector.
            "{ message.attr ->\n*[other] ok\n}",  # Message attribute selector.
            "{ -term ->\n*[other] ok\n}",  # Term selector.
        ):
            for fluent_type, attribute in (
                ("Message", False),
                ("Term", False),
                ("Message", True),
                ("Term", True),
            ):
                self.assert_syntax_error(
                    f"ok\n.attribute={value}" if attribute else value,
                    fluent_type,
                    error_message,
                )

        for value in (
            "[test string",  # Not allowed at start of a line
            "*test string",
            ".test string",
        ):
            for fluent_type in ("Message", "Term"):
                self.assert_syntax_error(value, fluent_type, error_message)

        # Duplicate attributes.
        self.assert_syntax_error(
            "ok\n.attr = ok\n.attr = ok",
            "Message",
            error_message,
        )

        # Invalid attribute name.
        self.assert_syntax_error(
            ".9attr = ok",
            "Message",
            error_message,
        )

        # Term with no value.
        self.assert_syntax_error(
            ".attr = ok",
            "Term",
            error_message,
        )


class FluentSourceSyntaxCheckTest(FluentCheckTestBase, FluentSyntaxCheckTestBase):
    check = FluentSourceSyntaxCheck()

    def assert_syntax_ok(self, value: str, fluent_type: str) -> None:
        self.assert_source_check_passes(self.check, value, fluent_type)

    def assert_syntax_error(
        self,
        value: str,
        fluent_type: str,
        description: str | re.Pattern,
    ) -> None:
        self.assert_source_check_fails(self.check, value, fluent_type, description)

    def test_untyped(self) -> None:
        # Units with no fluent-type: flag are assumed to be messages or terms
        # based on the id.
        source = ".attr = ok"
        unit = MockFluentTransUnit(
            source,
            target="",
            fluent_type=None,
            unit_id="message",
            is_source=True,
        )
        self.assertFalse(
            self.check.check_source_unit([source], unit),
            f"Syntax check should pass for {unit} with Message id",
        )
        unit = MockFluentTransUnit(
            source,
            target="",
            fluent_type=None,
            unit_id="-term",
            is_source=True,
        )
        self.assertTrue(
            self.check.check_source_unit([source], unit),
            f"Syntax check should fail for {unit} with Term id",
        )


class FluentTargetSyntaxCheckTest(FluentCheckTestBase, FluentSyntaxCheckTestBase):
    check = FluentTargetSyntaxCheck()

    def assert_syntax_ok(self, value: str, fluent_type: str) -> None:
        # Check is independent of the source value.
        self.assert_target_check_passes(self.check, "ok", value, fluent_type)

    def assert_syntax_error(
        self,
        value: str,
        fluent_type: str,
        description: str | re.Pattern,
    ) -> None:
        self.assert_target_check_fails(
            self.check, "ok", value, fluent_type, description
        )

    def test_untyped(self) -> None:
        # Units with no fluent-type: flag are assumed to be messages or terms
        # based on the id.
        source = "ok"
        target = ".attr = ok"
        unit = MockFluentTransUnit(
            source,
            target=target,
            fluent_type=None,
            unit_id="message",
            is_source=True,
        )
        self.assertFalse(
            self.check.check_single(source, target, unit),
            f"Syntax check should pass for {unit} with Message id",
        )
        unit = MockFluentTransUnit(
            source,
            target=target,
            fluent_type=None,
            unit_id="-term",
            is_source=True,
        )
        self.assertTrue(
            self.check.check_single(source, target, unit),
            f"Syntax check should fail for {unit} with Term id",
        )


class FluentPartsCheckTest(FluentCheckTestBase):
    check = FluentPartsCheck()

    def test_message_same_parts(self) -> None:
        for source, target in (
            ("source", "target"),
            (".attr = source", ".attr = target"),
            ("source\n.attr = ok", "target\n.attr = val"),
            # Differing whitespace in the syntax is ok.
            ("source\n.attr = ok", "target\n .attr=val"),
            # Two attributes.
            ("source\n.title = ok\n.alt = val", "target\n.title = val\n.alt = val2"),
            # Different order is technically ok.
            ("source\n.title = ok\n.alt = val", "target\n.alt = val2\n.title = val"),
            # No Message value, only attributes.
            (".title = ok\n.alt = val", ".title = val\n.alt = val2"),
            (".title = ok\n.alt = val", ".title = val\n.alt = val2"),
        ):
            self.assert_checks(source, target, "Message")

    def test_message_differing_parts(self) -> None:
        self.assert_target_check_fails(
            self.check,
            "source\n.attr = ok",
            "target",
            "Message",
            "Missing Fluent attribute: <code>.attr\xa0=\xa0…</code>",
        )
        self.assert_target_check_fails(
            self.check,
            "source",
            "target\n.attr = ok",
            "Message",
            "Unexpected Fluent attribute: <code>.attr\xa0=\xa0…</code>",
        )
        self.assert_target_check_fails(
            self.check,
            "source\n.title = ok",
            ".title = target",
            "Message",
            "Fluent value is empty.",
        )
        self.assert_target_check_fails(
            self.check,
            ".title = source",
            "target",
            "Message",
            "Fluent value should be empty.<br>"
            "Missing Fluent attribute: <code>.title\xa0=\xa0…</code>",
        )
        self.assert_target_check_fails(
            self.check,
            "value\n.title = source\n.alt = another",
            ".alt-not = ok\n.title = target",
            "Message",
            "Fluent value is empty.<br>"
            "Missing Fluent attribute: <code>.alt\xa0=\xa0…</code><br>"
            "Unexpected Fluent attribute: <code>.alt-not\xa0=\xa0…</code>",
        )
        self.assert_target_check_fails(
            self.check,
            ".title = source\n.alt = another",
            "title = target\n.alt = ok",
            "Message",
            "Fluent value should be empty.<br>"
            "Missing Fluent attribute: <code>.title\xa0=\xa0…</code>",
        )
        self.assert_target_check_fails(
            self.check,
            ".title = source\n.alt = another",
            ".titles = target\n.alts = ok",
            "Message",
            "Missing Fluent attribute: <code>.title\xa0=\xa0…</code><br>"
            "Missing Fluent attribute: <code>.alt\xa0=\xa0…</code><br>"
            "Unexpected Fluent attribute: <code>.titles\xa0=\xa0…</code><br>"
            "Unexpected Fluent attribute: <code>.alts\xa0=\xa0…</code>",
        )

    def test_syntax_error_in_parts(self) -> None:
        # If there is a syntax error in the source or target, we do not get a
        # missing parts error.

        for source, source_ok, target, target_ok in (
            ("source\n.attr = ok", True, "target {", False),
            ("source\n.attr = }", False, "target", True),
            ("source", True, "target\n.attr =", False),
            ("*source", False, "target\n.attr = ok", True),
            ("source\n.title = ok", True, ".title = target { -term.attr }", False),
            ("source { mes@g }\n.title = ok", False, ".title = target", True),
            (".title = source", True, "target { .5 }", False),
            (".title@ = source", False, "target", True),
            ("source {", False, ".attr = target {", False),
        ):
            self.assert_checks(
                source,
                target,
                "Message",
                {
                    FluentPartsCheck: True,
                    FluentSourceSyntaxCheck: source_ok,
                    FluentTargetSyntaxCheck: target_ok,
                },
            )

    def test_term_parts(self) -> None:
        # The check will never fail for Terms because missing a value is a
        # syntax check and Term attributes are considered locale-specific.

        for source, source_ok, target, target_ok in (
            # Syntax errors without value.
            (".type = source", False, "target", True),
            ("source", True, ".type = target", False),
            # Different attributes is ok.
            ("source\n.attr = ok", True, "target", True),
            ("source", True, "target\n.attr1 = ok\n.attr2 = ok", True),
        ):
            self.assert_checks(
                source,
                target,
                "Term",
                {
                    FluentPartsCheck: True,
                    FluentSourceSyntaxCheck: source_ok,
                    FluentTargetSyntaxCheck: target_ok,
                },
            )

    def test_untyped(self) -> None:
        # Units with no fluent-type: flag are assumed to be messages or terms
        # based on the id.
        source = "source\n.title = ok"
        target = "target"
        unit = MockFluentTransUnit(
            source,
            target=target,
            fluent_type=None,
            unit_id="message",
            is_source=True,
        )
        self.assertTrue(
            self.check.check_single(source, target, unit),
            f"Parts check should fail for {unit} with Message id",
        )
        unit = MockFluentTransUnit(
            source,
            target=target,
            fluent_type=None,
            unit_id="-term",
            is_source=True,
        )
        self.assertFalse(
            self.check.check_single(source, target, unit),
            f"Parts check should pass for {unit} with Term id",
        )

    def test_parts_highlight(self) -> None:
        # Nothing to highlight for the value part.
        self.assert_source_highlights(self.check, "source", "Message", [])
        # Highlight the attribute syntax.
        self.assert_source_highlights(
            self.check,
            "source\n.alt = attribute",
            "Message",
            [(7, ".alt =")],
        )
        # With different whitespace.
        self.assert_source_highlights(
            self.check,
            "source\n .alt=attribute",
            "Message",
            [(7, " .alt=")],
        )
        # Only highlight the actual attribute syntax, even if the same
        # characters appear elsewhere.
        self.assert_source_highlights(
            self.check,
            "source .alt = ok\n.alt = attribute",
            "Message",
            [(17, ".alt =")],
        )
        # Two attributes.
        self.assert_source_highlights(
            self.check,
            "source\n.alt = attribute\n.title = ok",
            "Message",
            [(7, ".alt ="), (24, ".title =")],
        )

        # No part highlights if broken syntax.
        self.assert_source_highlights(
            self.check, "source\n.alt = attribute {", "Message", []
        )

        # No highlights for Terms.
        self.assert_source_highlights(self.check, "source", "Term", [])
        self.assert_source_highlights(self.check, "source\n.type = ok", "Term", [])


class TestFluentReferencesCheck(FluentCheckTestBase):
    check = FluentReferencesCheck()

    def test_same_refs(self) -> None:
        for matching_sources in (
            ("source", "target"),
            ("source { $var }", "{ $var } target"),
            ("source { message }", "target { message }"),
            ("{ other-msg.alt } source", "target { other-msg.alt }"),
            ("source { -term } ok", "target { -term }"),
            # Term parameters do not need to match.
            ("source { -term } ok", 'target { -term(param: "ok") }'),
            ('source { -term(attr: "a", var: "b") } ok', "target { -term }"),
            # References within a function is ok.
            ("source { FUNCTION($var, 5) }", "{ $var } target"),
            ("source { FUNCTION(3, $num) }", '{ OTHER($num, x: "ok") }'),
            # Literal placeables are not references.
            ('source { "literal" }', "target"),
            ("source", "target { 3.5 }"),
            # Something that looks like a reference within a literal is not a
            # reference.
            ("source", 'target { "{ $var }" }'),
            # Different whitespace.
            ("source { message }", "target {\n  message\n}"),
            ("source {message}", "target { message }"),
            # Multiple refs.
            ("sent { $n } to { -term }", "{ $n } target { -term }"),
            ("{ $num1 } > { $num2 }", "{ $num1 } exceeds { $num2 }"),
            # Order is not important.
            ("{ $num1 } > { $num2 }", "{ $num2 } < { $num1 }"),
            # Same refs appears multiple times.
            ("{ $num }, { $num }", "{ $num } with { $num }"),
            # With selectors.
            (
                "with { -term }",
                "with { -term.starts-with-vowel ->\n"
                "  [yes] an { -term }\n"
                " *[no] a { -term }\n"
                "}",
                "with { -term.starts-with-vowel ->\n  [yes] an\n *[no] a\n} { -term }",
                "with { PLATFORM() ->\n  [linux] { -term }!\n *[other] { -term }\n}",
                "with { -term.starts-with-vowel ->\n"
                "  [yes] an { -term }\n"
                " *[no] a { PLATFORM() ->\n"
                "    [linux] { -term }!\n"
                "   *[other] { -term }\n"
                "  }\n"
                "} more",
            ),
            (
                "with { $var }",
                "with { $var ->\n"
                "  [one] { $var } variable\n"
                " *[other] { $var } variables\n"
                "}",
                # $var is optional in the branch where we split over $var if the
                # other branch contains it.
                "with { $var ->\n"
                "  [one] a variable\n"
                " *[some] some variables\n"
                "  [other] { $var } variables\n"
                "}",
                "with { $var ->\n"
                "  [one] a variable\n"
                "  [some] { NUMBER($var, param: 0) } variables\n"
                " *[other] { $var } variables\n"
                "}",
                "with { $var ->\n"
                "  [one] a variable\n"
                " *[other] { FUNC($var) } variables\n"
                "}",
                # Extra variable in the selector is ok.
                "with { FUNC2($var, $var2) ->\n"
                "  [one] a variable\n"
                " *[other] { $var } variables\n"
                "}",
                # Appearing twice in the selector is ok.
                "with { FUNC2($var, $var) ->\n"
                "  [one] a variable\n"
                " *[other] { $var } variables\n"
                "}",
                "with { $var }{ $var ->\n  [one] variable\n *[other] variables\n}",
                # $var that is two selection expressions up still gets shared as
                # long as each variant below has the same number of refs.
                "with { $var ->\n"
                "  [one] a variable\n"
                " *[other] { PLATFORM() ->\n"
                "    [linux] { $var } variables!\n"
                "   *[other] { $var } variables\n"
                "  }\n"
                "}",
            ),
            (
                # Two refs.
                "{ $num } and { message }",
                "{ $num ->\n"
                "  [one] { $num } is { message }\n"
                " *[other] { $num } are { message }\n"
                "}",
                "{ $num ->\n  [one] { $num } is\n *[other] { $num } are\n} { message }",
                "{ $num ->\n"
                "  [one] a person is { message }\n"
                " *[other] { $num } people are { message }\n"
                "}",
                "{ $num ->\n"
                "  [one] a person\n"
                " *[other] { $num } people\n"
                "} really { $num ->\n"
                "  [one] is { message }\n"
                " *[other] are { message }\n"
                "}",
                "{ message } for { $num ->\n"
                "  [one] a person\n"
                " *[other] { $num } people\n"
                "}",
                "{ $num ->\n"
                "  [one] a person is { message }\n"
                " *[other] { $num ->\n"
                "    [2] a pair of people are { message }\n"
                "   *[other] { $num } people are { message }\n"
                "  }\n"
                "}",
            ),
            (
                # Two variable refs.
                "{ $num } and { $var }",
                "{ $num ->\n"
                "  [zero] none\n"
                " *[other] { $num }\n"
                "} and { $var ->\n"
                " *[yes] { $var }\n"
                "  [no] none\n"
                "}",
                "{ $num ->\n"
                "  [zero] none and { $var ->\n"
                "   *[no] none\n"
                "    [yes] { $var }"
                "    [third] nope\n"
                "  }\n"
                " *[other] { $num } and { $var ->\n"
                "   *[yes] { $var }\n"
                "    [no] nothing\n"
                "  }\n"
                "}",
                # If both refs appear in the same selector, they can both be
                # shared amongst the branches.
                "{ FUNC($num, $var) ->\n"
                "  [0] nothing\n"
                " *[other] { $num } are { $var }\n"
                "}",
                "{ FUNC($var, $num) ->\n"
                "  [0] nothing { $var }\n"
                "  [1] a { $var }\n"
                " *[other] just { $num }\n"
                "}",
                "{ FUNC($var, $num) ->\n"
                "  [0] nothing { $var }\n"
                "  [1] a { $num }\n"
                " *[other] just { $num } and { $var }\n"
                "}",
                "{ FUNC($num, $var) ->\n"
                "  [zero] none\n"
                " *[other] { $num } and { $var ->\n"
                "   *[yes] { $var }\n"
                "    [no] nothing\n"
                "  }\n"
                "}",
                "{ FUNC($num, $var) ->\n"
                "  [zero] { $var ->\n"
                "    [a] nothing\n"
                "   *[b] { $var }\n"
                "  }\n"
                " *[other] { $num ->\n"
                "   *[other] { $num }\n"
                "    [zero] nothing\n"
                "  }\n"
                "}",
            ),
            (
                # Same ref appears twice, it will also be shared across
                # variants.
                "{ $num } and { $num }",
                "{ $num ->\n  [zero] none\n *[other] { $num } and { $num }\n}",
                "{ $num ->\n"
                "  [zero] none\n"
                "  [one] just { $num }\n"
                " *[other] { $num } and { $num }\n"
                "}",
                "{ $num ->\n"
                "  [zero] none\n"
                " *[other] { $num } and { $num ->\n"
                "    [2] a pair\n"
                "   *[other] { $num }\n"
                "  }\n"
                "}",
                "{ $num ->\n"
                "  [zero] none\n"
                " *[other] have { $num ->\n"
                "    [2] a pair\n"
                "   *[other] { $num } and { $num }\n"
                "  }\n"
                "}",
            ),
            (
                # Have two variants with different refs, just need at least one
                # match for each set of refs.
                "value { PLATFORM() ->\n  [linux] none\n *[other] with { -term }\n}",
                "value { PLATFORM() ->\n"
                "  [linux] none\n"
                "  [macos] and { -term }\n"
                " *[other] with { -term }\n"
                "}",
                "value { -term.attr ->\n"
                "  [a] none\n"
                "  [b] another\n"
                " *[c] with { -term }\n"
                "}",
                "value { -term.attr ->\n"
                "  [a] none\n"
                "  [b] another\n"
                " *[c] with { -term }\n"
                "} and { $var ->\n"
                "  [one] some more\n"
                " *[other] a lot\n"
                "}",
            ),
            (
                # Have three variants.
                "{ $var ->\n"
                " *[a] a { $num } and { -term }\n"
                "  [b] { message.title } and b { $num }\n"
                "  [c] c { $num }\n"
                "}",
                "{ $var ->\n"
                " *[a] a { $num } and { -term }\n"
                "  [b] { message.title } and b { $num }\n"
                "  [c] c { $num }\n"
                "  [d] d { -term } and { $num }\n"
                "}",
                "{ $var ->\n"
                " *[a] a\n"
                "  [b] { message.title }\n"
                "  [c] c { -term }\n"
                "} and { $num ->\n"
                "  [one] single\n"
                " *[other] { $num }\n"
                "}",
                # Selector references are still shared amongst branches with
                # different references.
                "{ $num ->\n"
                " *[other] a { $num } and { -term }\n"
                "  [zero] none\n"
                "  [one] { message.title }\n"
                "}",
                "{ $var ->\n"
                " *[a] a { $num ->\n"
                "    [one] { -term }\n"
                "   *[other] { $num } { -term }\n"
                "  } more\n"
                "  [b] { message.title } and b { $num }\n"
                "  [c] c { $num }\n"
                "}",
            ),
        ):
            # The check should be transitive and symmetric, so the check should
            # pass for all pairs compared against each other.
            for source, target in itertools.permutations(matching_sources, 2):
                # Values for Terms and Messages are compared.
                self.assert_checks(source, target, "Term")
                self.assert_checks(source, target, "Message")
                # Message attributes only compared with matching attributes.
                self.assert_checks(
                    f"source {{ $var }}\n.alt = {source}",
                    f"{{ $var }}target\n.alt = {target}",
                    "Message",
                )

        # Message parts that do not match are not checked.
        self.assert_checks(
            "source { $var }\n.alt = { $var }",
            "target { $var }\n.title = { -term }",
            "Message",
            {
                FluentPartsCheck: False,
                FluentReferencesCheck: True,
            },
        )
        # Value missing in target.
        self.assert_checks(
            ".title = source { message.attr }",
            "{ $var }\n.title = { message.attr } target",
            "Message",
            {
                FluentPartsCheck: False,
                FluentReferencesCheck: True,
            },
        )
        # Value missing in source.
        self.assert_checks(
            ".title = { -term }",
            "{ -term } and { $var }\n.title = also { -term }",
            "Message",
            {
                FluentPartsCheck: False,
                FluentReferencesCheck: True,
            },
        )

        # Term attributes are not compared.
        # NOTE: We do not expect any references within a Term attribute, but
        # they are technically allowed by the syntax.
        self.assert_checks("source", "target\n.type = { message }", "Term")
        self.assert_checks("source\n.tense = { -t } and { $var }", "target", "Term")
        self.assert_checks(
            "source\n.tense = { $num }",
            "target\n.tense = no refs",
            "Term",
        )
        self.assert_checks(
            "source\n.tense = no refs",
            "target\n.tense = { -term }",
            "Term",
        )

    def test_different_refs(self) -> None:
        for fluent_type in ("Message", "Term"):
            self.assert_target_check_fails(
                self.check,
                "source { $var }",
                "target",
                fluent_type,
                "Fluent value is missing a "
                "<code>{\xa0$var\xa0}</code> Fluent reference.",
            )
            self.assert_target_check_fails(
                self.check,
                "source",
                "target { -term }",
                fluent_type,
                "Fluent value has an unexpected extra "
                "<code>{\xa0-term\xa0}</code> Fluent reference.",
            )
            self.assert_target_check_fails(
                self.check,
                "source { message }",
                "target { message.attr }",
                fluent_type,
                "Fluent value is missing a <code>{\xa0message\xa0}</code> "
                "Fluent reference.<br>"
                "Fluent value has an unexpected extra "
                "<code>{\xa0message.attr\xa0}</code> Fluent reference.",
            )
            self.assert_target_check_fails(
                self.check,
                "{ NUMBER($var) } source",
                "target",
                fluent_type,
                "Fluent value is missing a "
                "<code>{\xa0$var\xa0}</code> Fluent reference.",
            )
            # Reference in literal does not count.
            self.assert_target_check_fails(
                self.check,
                'source { "{ -term }" }',
                "target { -term }",
                fluent_type,
                "Fluent value has an unexpected extra "
                "<code>{\xa0-term\xa0}</code> Fluent reference.",
            )
            # Multiple references.
            self.assert_target_check_fails(
                self.check,
                "source { -term } with { message } and { $var }",
                "target { message } with { -terms }",
                fluent_type,
                "Fluent value is missing a "
                "<code>{\xa0-term\xa0}</code> Fluent reference.<br>"
                "Fluent value is missing a "
                "<code>{\xa0$var\xa0}</code> Fluent reference.<br>"
                "Fluent value has an unexpected extra "
                "<code>{\xa0-terms\xa0}</code> Fluent reference.",
            )
            # Same reference appears multiple times.
            self.assert_target_check_fails(
                self.check,
                "source { -term } with { -term }",
                "target { -term }",
                fluent_type,
                "Fluent value is missing a "
                "<code>{\xa0-term\xa0}</code> Fluent reference.",
            )
            self.assert_target_check_fails(
                self.check,
                "source { -term }",
                "target { -term } with { -term(param: 5) }",
                fluent_type,
                "Fluent value has an unexpected extra "
                "<code>{\xa0-term\xa0}</code> Fluent reference.",
            )

            # With selectors, where the source only has one set of references
            # amongst all of its variants.

            for source in (
                # All have the same refs.
                "source { $num }",
                "source { NUMBER($num) }",
                "source { PLATFORM() ->\n"
                "  [linux] { $num }!\n"
                "  [macos] { $num }?\n"
                " *[rest] { $num }\n"
                "}",
                "source { $num ->\n  [zero] nothing\n *[other] { $num }\n}",
            ):
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "{ $nums }",
                    fluent_type,
                    # Even though we have multiple source variants, they each
                    # have the same references so this is compared against just
                    # that common set.
                    "Fluent value is missing a <code>{\xa0$num\xa0}</code> "
                    "Fluent reference.<br>"
                    "Fluent value has an unexpected extra "
                    "<code>{\xa0$nums\xa0}</code> Fluent reference.",
                )
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "{ $num } plus { $num }",
                    fluent_type,
                    "Fluent value has an unexpected extra "
                    "<code>{\xa0$num\xa0}</code> Fluent reference.",
                )
                # Target has multiple variants with the same references.
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "{ PLATFORM() ->\n  [linux] a { num }\n *[other] b { num }\n}",
                    fluent_type,
                    # Even though we have multiple target variants, they each
                    # have the same missing and extra refs, so the variants are
                    # not mentioned.
                    "Fluent value is missing a <code>{\xa0$num\xa0}</code> "
                    "Fluent reference.<br>"
                    "Fluent value has an unexpected extra "
                    "<code>{\xa0num\xa0}</code> Fluent reference.",
                )

                # When variants in the target differer.
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "{ $var ->\n  [yes] { $num }\n *[no] { -term }\n}",
                    fluent_type,
                    "Fluent value is missing a <code>{\xa0$num\xa0}</code> "
                    "Fluent reference for the following variants: "
                    "<code>[no]</code>.<br>"
                    "Fluent value has an unexpected extra "
                    "<code>{\xa0-term\xa0}</code> Fluent reference for the "
                    "following variants: <code>[no]</code>.",
                )
                # One variant has too many whilst the other has too little.
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "{ $var ->\n"
                    "  [yes] { $num } and { $num } and { $num }\n"
                    " *[no] none\n"
                    "}",
                    fluent_type,
                    "Fluent value is missing a <code>{\xa0$num\xa0}</code> "
                    "Fluent reference for the following variants: "
                    "<code>[no]</code>.<br>"
                    "Fluent value has an unexpected extra "
                    "<code>{\xa0$num\xa0}</code> Fluent reference for the "
                    "following variants: <code>[yes]</code>.",
                )
                # With nested selectors.
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "{ $var ->\n"
                    "  [yes] { $num }\n"
                    " *[no] { $num ->\n"
                    "    [one] a { -term }\n"
                    "   *[other] { $num }\n"
                    "  }\n"
                    "}",
                    fluent_type,
                    # NOTE: [no][one] is not missing a ref because the $num ref
                    # is shared.
                    "Fluent value has an unexpected extra "
                    "<code>{\xa0-term\xa0}</code> Fluent reference for the "
                    "following variants: <code>[no][one]</code>.",
                )
                # Reference only in selector does not count.
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "target { $num ->\n*[other] val\n}",
                    fluent_type,
                    "Fluent value is missing a <code>{\xa0$num\xa0}</code> "
                    "Fluent reference.",
                )
                # A ref will not be shared amongst variants if it does not match
                # the selector.
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "target { $other-var ->\n[one] none\n*[other] { $num }\n}",
                    fluent_type,
                    "Fluent value is missing a <code>{\xa0$num\xa0}</code> "
                    "Fluent reference for the following variants: "
                    "<code>[one]</code>.",
                )
                # Similarly, the ref will not be shared one level up either,
                # even if that does match the selector.
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "{ $num ->\n"
                    "  [one] none\n"
                    " *[other] { $var ->\n"
                    "    [yes] { $num }\n"
                    "   *[no] nothing\n"
                    "  }\n"
                    "}",
                    fluent_type,
                    "Fluent value is missing a <code>{\xa0$num\xa0}</code> "
                    "Fluent reference for the following variants: "
                    "<code>[one], [other][no]</code>.",
                )
                # Won't share if it contains an extra ref either.
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "{ $num ->\n"
                    "  [one] none\n"
                    " *[other] { $var ->\n"
                    "    [yes] { $num } and { $num }\n"
                    "   *[no] { $num }\n"
                    "  }\n"
                    "}",
                    fluent_type,
                    "Fluent value is missing a <code>{\xa0$num\xa0}</code> "
                    "Fluent reference for the following variants: "
                    "<code>[one]</code>.<br>"
                    "Fluent value has an unexpected extra "
                    "<code>{\xa0$num\xa0}</code> Fluent reference for the "
                    "following variants: <code>[other][yes]</code>.",
                )
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "{ $var ->\n  [one] a { $num }\n *[other] { $var } { $num }\n}",
                    fluent_type,
                    # Even though the $var ref is shared between the variants,
                    # since it is an extra ref we do not report it for the
                    # [one] variant.
                    "Fluent value has an unexpected extra "
                    "<code>{\xa0$var\xa0}</code> Fluent reference for the "
                    "following variants: <code>[other]</code>.",
                )

            for source in (
                "{ $num } and { $var }",
                "{ $var ->\n  *[yes] { $num } and { $var }\n   [no] { $num }\n}",
                "{ $num ->\n"
                "  *[other] { $num }\n"
                "   [0] none\n"
                "} and { $var ->\n"
                '  [no] { "" }\n'
                " *[yes] { $var }\n"
                "}",
                "{ FUNC($num, $var) ->\n"
                "  *[yes] { $num } and { $var }\n"
                "   [maybe] { $num }\n"
                "   [no] nothing\n"
                "}",
            ):
                # If a sub-selector does not share the same references, it will
                # not be shared across super-selectors either.
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "{ FUNC($num, $var) ->\n"
                    "  [one] none\n"
                    " *[other] { $var ->\n"
                    "    [yes] { $num } and { $var }\n"
                    "   *[no] nothing\n"
                    "  }\n"
                    "}",
                    fluent_type,
                    "Fluent value is missing a <code>{\xa0$num\xa0}</code> "
                    "Fluent reference for the following variants: "
                    "<code>[one], [other][no]</code>.<br>"
                    # [one] is reported as missing $var as well since this is
                    # not shared because $num cannot be shared.
                    # [other][no] is not reported as missing $var because it was
                    # shared over the second selector.
                    "Fluent value is missing a <code>{\xa0$var\xa0}</code> "
                    "Fluent reference for the following variants: "
                    "<code>[one]</code>.",
                )
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "{ FUNC($num, $var) ->\n"
                    "  [a] { $num ->\n"
                    "    [x1] { $var }\n"
                    "   *[y1] none\n"
                    "  }\n"
                    " *[b] { $var } and { $var ->\n"
                    "    [x2] { $num }\n"
                    "   *[y2] nothing\n"
                    "  }\n"
                    "}",
                    fluent_type,
                    "Fluent value is missing a <code>{\xa0$num\xa0}</code> "
                    "Fluent reference for the following variants: "
                    "<code>[a][x1], [a][y1], [b][y2]</code>.<br>"
                    "Fluent value is missing a <code>{\xa0$var\xa0}</code> "
                    "Fluent reference for the following variants: "
                    "<code>[a][y1]</code>.",
                )
                # With 6 variants.
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "{ $var ->\n"
                    " *[other] { $num }\n"
                    "  [one] none\n"
                    "  [few] none\n"
                    "} and { FUNC() ->\n"
                    "  [yes] { $var }\n"
                    " *[no] { $vars }\n"
                    "}",
                    fluent_type,
                    "Fluent value is missing a <code>{\xa0$num\xa0}</code> "
                    "Fluent reference for the following variants: "
                    "<code>[one][yes], [few][yes], [one][no], "
                    "[few][no]</code>.<br>"
                    "Fluent value is missing a <code>{\xa0$var\xa0}</code> "
                    "Fluent reference for the following variants: "
                    "<code>[other][no], [one][no], [few][no]</code>.<br>"
                    "Fluent value has an unexpected extra "
                    "<code>{\xa0$vars\xa0}</code> Fluent reference for the "
                    "following variants: <code>[other][no], [one][no], "
                    "[few][no]</code>.",
                )

            # When the source has variants with different refs the error
            # messages are more generic.
            self.assert_target_check_fails(
                self.check,
                "{ FUNC() ->\n"
                "  [a] { msg.attr } and { -term }\n"
                " *[b] { msg } and { -term }\n"
                "}",
                "{ msg } and { -term }",
                fluent_type,
                "The following variants in the original Fluent value do not "
                "have at least one matching variant in the translation with "
                "the same set of Fluent references: <code>[a]</code>.",
            )
            self.assert_target_check_fails(
                self.check,
                "{ FUNC() ->\n"
                "  [a] { msg.attr } and { -term }\n"
                " *[b] { msg } and { -term }\n"
                "} and { -term }",
                "{ -term }",
                fluent_type,
                "The following variants in the original Fluent value do not "
                "have at least one matching variant in the translation with "
                "the same set of Fluent references: <code>[a], [b]</code>.<br>"
                "The translated Fluent value does not have a matching variant "
                "in the original with the same set of Fluent references.",
            )
            self.assert_target_check_fails(
                self.check,
                "{ $n ->\n  [a] { $n } and { -term }\n *[b] { message }\n}",
                "{ $n ->\n  [x] { $n } and { message }\n *[y] { $ns } and { -term }\n}",
                fluent_type,
                "The following variants in the original Fluent value do not "
                "have at least one matching variant in the translation with "
                "the same set of Fluent references: <code>[a]</code>.<br>"
                "The following variants in the translated Fluent value do not "
                "have a matching variant in the original with the same set of "
                "Fluent references: <code>[y]</code>.",
            )
            self.assert_target_check_fails(
                self.check,
                "{ $n ->\n  [a] { $n } and { -term }\n *[b] { message }\n}",
                "{ $n ->\n"
                "  [x] { $n } and { message }\n"
                " *[y] { $n } and { -term }\n"
                "} and { FUNC() ->\n"
                "  [one] { -term }\n"
                " *[other] none\n"
                "}",
                fluent_type,
                "The following variants in the translated Fluent value do not "
                "have a matching variant in the original with the same set of "
                "Fluent references: <code>[x][one], [y][one]</code>.",
            )
            self.assert_target_check_fails(
                self.check,
                "{ $n ->\n"
                " *[other] { $n } and { $n }\n"
                "  [zero] none\n"
                "} and { FUNC() ->\n"
                "  [a] { -term }\n"
                " *[b] { message }\n"
                "}",
                "{ $n ->\n"
                " *[other] { $n }\n"
                "  [zero] none\n"
                "} and { FUNC() ->\n"
                "  [a] { -term }\n"
                " *[b] { message }\n"
                "}",
                fluent_type,
                "The following variants in the original Fluent value do not "
                "have at least one matching variant in the translation with "
                "the same set of Fluent references: <code>"
                "[other][a], [zero][a], [other][b], [zero][b]</code>.<br>"
                "The following variants in the translated Fluent value do not "
                "have a matching variant in the original with the same set of "
                "Fluent references: <code>"
                "[other][a], [zero][a], [other][b], [zero][b]</code>.",
            )

        # With Message attributes.
        self.assert_target_check_fails(
            self.check,
            ".title = { $var }",
            ".title = none",
            "Message",
            "Fluent <code>title</code> attribute is missing a "
            "<code>{\xa0$var\xa0}</code> Fluent reference.",
        )

        self.assert_target_check_fails(
            self.check,
            ".title = none",
            ".title = { -term }",
            "Message",
            "Fluent <code>title</code> attribute has an unexpected extra "
            "<code>{\xa0-term\xa0}</code> Fluent reference.",
        )

        # Mix of value and attributes.
        self.assert_target_check_fails(
            self.check,
            "{ $num ->\n"
            " *[other] { $num } and { $num }\n"
            "  [zero] none\n"
            "}\n"
            ".alt = Alt with { -term }\n"
            ".title = none",
            "{ $num ->\n"
            " *[other] one { $num }\n"
            "  [zero] none\n"
            "}\n"
            ".alt = { -terms }\n"
            ".title = { msg.attr }\n",
            "Message",
            "Fluent value is missing a <code>{\xa0$num\xa0}</code> "
            "Fluent reference.<br>"
            "Fluent <code>alt</code> attribute is missing a "
            "<code>{\xa0-term\xa0}</code> Fluent reference.<br>"
            "Fluent <code>alt</code> attribute has an unexpected extra "
            "<code>{\xa0-terms\xa0}</code> Fluent reference.<br>"
            "Fluent <code>title</code> attribute has an unexpected extra "
            "<code>{\xa0msg.attr\xa0}</code> Fluent reference.",
        )

        # With all source variants having the same references, but target
        # variants do not.
        self.assert_target_check_fails(
            self.check,
            ".label = { $num ->\n"
            "  *[other] { $num } tabs\n"
            "   [one] { $num } tab\n"
            "} for { -term.attr ->\n"
            '  [a] { -term(param: "yes") }\n'
            ' *[b] { -term(param: "no") }\n'
            "}",
            ".label = { $num ->\n"
            "  *[other] { FUNC($nums) ->\n"
            "     [2] { $num } tabs\n"
            "    *[other] { $nums } tabs\n"
            "   }\n"
            "   [one] a tab\n"
            "} for { -term }",
            "Message",
            "Fluent <code>label</code> attribute is missing a "
            "<code>{\xa0$num\xa0}</code> Fluent reference for the following "
            "variants: <code>[other][other], [one]</code>.<br>"
            "Fluent <code>label</code> attribute has an unexpected extra "
            "<code>{\xa0$nums\xa0}</code> Fluent reference for the following "
            "variants: <code>[other][other]</code>.",
        )

        # With source variants having different references.
        self.assert_target_check_fails(
            self.check,
            ".title = { PLATFORM() ->\n  [linux]  with { -term }\n *[other] none\n}",
            ".title = { -terms }",
            "Message",
            "The following variants in the original Fluent <code>title</code> "
            "attribute do not have at least one matching variant in the "
            "translation with the same set of Fluent references: "
            "<code>[linux], [other]</code>.<br>"
            "The translated Fluent <code>title</code> attribute does not "
            "have a matching variant in the original with the same "
            "set of Fluent references.",
        )
        self.assert_target_check_fails(
            self.check,
            ".title = { PLATFORM() ->\n"
            "  [linux] { message } with { $var }\n"
            " *[other] none\n"
            "}",
            ".title = { PLATFORM() ->\n"
            "  [linux] { message }\n"
            " *[other] none\n"
            "} with { FUNC() ->\n"
            "  [yes] { $var }\n"
            " *[no] none\n"
            "}",
            "Message",
            "The following variants in the translated Fluent "
            "<code>title</code> attribute do not have a matching variant in "
            "the original with the same set of Fluent references: "
            "<code>[other][yes], [linux][no]</code>.",
        )

        # If we are missing a parts, we still get errors for the parts that are
        # there.
        source = "{ $var }\n.title = { $var }\n.alt = { -term }"
        target = "\n.title = { NUMBER($vars) }\n.label = { -terms }"
        self.assert_target_check_fails(
            FluentPartsCheck(),
            source,
            target,
            "Message",
            "Fluent value is empty.<br>"
            "Missing Fluent attribute: <code>.alt\xa0=\xa0…</code><br>"
            "Unexpected Fluent attribute: <code>.label\xa0=\xa0…</code>",
        )
        self.assert_target_check_fails(
            self.check,
            source,
            target,
            "Message",
            "Fluent <code>title</code> attribute is missing a "
            "<code>{\xa0$var\xa0}</code> Fluent reference.<br>"
            "Fluent <code>title</code> attribute has an unexpected extra "
            "<code>{\xa0$vars\xa0}</code> Fluent reference.",
        )

    def test_with_syntax_error(self) -> None:
        # If there is a syntax error in the source or target, we do not get a
        # reference error.

        for source, source_ok, target, target_ok in (
            ("source { message }", True, "target {", False),
            ("source\n.attr = }", False, "target { -term }", True),
            (".title = source { $var }", True, ".title =", False),
        ):
            self.assert_checks(
                source,
                target,
                "Message",
                {
                    FluentReferencesCheck: True,
                    FluentSourceSyntaxCheck: source_ok,
                    FluentTargetSyntaxCheck: target_ok,
                },
            )

    def test_untyped(self) -> None:
        # Units with no fluent-type: flag are assumed to be messages or terms
        # based on the id.
        source = "source\n.title = { -term }"
        target = "target\n.title = { $var }"
        unit = MockFluentTransUnit(
            source,
            target=target,
            fluent_type=None,
            unit_id="message",
            is_source=True,
        )
        self.assertTrue(
            self.check.check_single(source, target, unit),
            f"References check should fail for {unit} with Message id",
        )
        unit = MockFluentTransUnit(
            source,
            target=target,
            fluent_type=None,
            unit_id="-term",
            is_source=True,
        )
        self.assertFalse(
            self.check.check_single(source, target, unit),
            f"References check should pass for {unit} with Term id",
        )

    def test_references_highlight(self) -> None:
        self.assert_source_highlights(self.check, "source", "Message", [])
        self.assert_source_highlights(
            self.check,
            "my { $var } ref",
            "Message",
            [(3, "{ $var }")],
        )
        # Different whitespace.
        self.assert_source_highlights(
            self.check,
            "my {\n$var } ref",
            "Message",
            [(3, "{\n$var }")],
        )
        self.assert_source_highlights(
            self.check,
            "my {$var\n} ref",
            "Message",
            [(3, "{$var\n}")],
        )
        self.assert_source_highlights(
            self.check,
            ".title = my { message } ref",
            "Message",
            [(12, "{ message }")],
        )
        self.assert_source_highlights(
            self.check,
            "a { msg.attr }\n.title = my { -term } ref",
            "Message",
            [(2, "{ msg.attr }"), (27, "{ -term }")],
        )
        # With term parameters.
        self.assert_source_highlights(
            self.check,
            'a { -term(param: "hello", param2: 3.5) } ref',
            "Message",
            [(2, '{ -term(param: "hello", param2: 3.5) }')],
        )
        # Different whitespace.
        self.assert_source_highlights(
            self.check,
            'a { -term( param : "hello",param2:3.5, ) } ref',
            "Message",
            [(2, '{ -term( param : "hello",param2:3.5, ) }')],
        )

        # Ref within a func is not yet highlighted.
        self.assert_source_highlights(
            self.check,
            "a { NUMBER($var) } ref",
            "Message",
            [],
        )
        # But wrapping in placeable brackets will make it highlighted.
        self.assert_source_highlights(
            self.check,
            "a { NUMBER({ $var }) } ref",
            "Message",
            [(11, "{ $var }")],
        )
        # With a selector.
        self.assert_source_highlights(
            self.check,
            "value { -term }\n"
            ".alt = { $num ->\n"
            "  *[other] { $num } tabs\n"
            "   [one] { $num } tab\n"
            "}",
            "Message",
            [
                (6, "{ -term }"),
                (44, "{ $num }"),
                (67, "{ $num }"),
            ],
        )

        # Do not highlight a literal.
        self.assert_source_highlights(
            self.check,
            'literal { "{ $var }" } and not: { -term() } or { $var }',
            "Message",
            [(32, "{ -term() }"), (47, "{ $var }")],
        )

        # No part highlights if broken syntax.
        self.assert_source_highlights(self.check, "source { $var } {", "Message", [])

        # For Terms, only highlight references found in the value.
        self.assert_source_highlights(
            self.check,
            "source { message.attr }\n.alt = { $var }",
            "Term",
            [(7, "{ message.attr }")],
        )


class FluentInnerHTMLCheckTestBase:
    """
    Tests we want to run for both source and target inner HTML checks.

    The fluent inner HTML checks should act the same on both source and targets,
    we want to run the same tests.
    """

    def assert_html_ok(self, value: str, fluent_type: str) -> None:
        raise NotImplementedError

    def assert_html_error(
        self,
        value: str,
        fluent_type: str,
        description: str,
    ) -> None:
        raise NotImplementedError

    def test_html_ok(self) -> None:
        for value in (
            "Test string",
            "Test <span>string</span> more",
            "<h1>heading</h1>",
            # Whitespace in tag.
            "<p >inner</p  >",
            "<p\n>inner</p\t \n>",
            # Void elements.
            "void <img> element",
            "void <ImG> element",
            "void <img\t> element",
            "void <br/> element",
            "void <br \n/> element",
            # Multiple elements.
            "<span>first</span> and <em>second</em>",
            # Basic custom element names.
            "<custom-el>inner</custom-el>",
            # Attributes with quoted values.
            '<h3 class="ok">heading</h3>',
            "<h3 data-val='some val'>heading</h3>",
            "<h3  \ndata-val='some val'\n >heading</h3>",
            "<img data-val='some val'>none",
            "<img data-val='some val'/>none",
            "<img \t \ndata-val='some val' \t >none",
            "<img \n data-val='some val' />none",
            # Different case.
            "with <SPAN>capitals</SPAN> or <sPaN>mix</sPaN>",
            "with <span DATA-val='something'></span>",
            # Can include a "'" in double quotes.
            "before <img data-val1=\"val'ue\" other='ok'/> after",
            # And '"' in single quotes.
            'before <my-img data-val=\'val"ue\' other="ok"></my-img> after',  # codespell:ignore
            # Empty values.
            "<img data-empty=''/>",
            '<my-img data-empty=""></my-img>',
            # Sub-elements.
            "<p>test<br>sub-<strong><em>el</em>ements</strong></p>",
            "<div><h1 class='ok'>heading</h1></div> and <div>val<br>ue</div>",  # codespell:ignore
            # HTML character references.
            "test&lt;string&AMP;ok",
            "test <img val='x&#x27;\"'> string",
            'test <span val="&quot;hello&quot;">hello</span> string',
            "test <div>a&#60;b</div> string",
            "test &dot;&doteq;&doteqdot;",
            # Right angle by itself is ok.
            "a>b",
            "a!b",
            "a?b",
            "test <div>hel/>lo</div>",  # codespell:ignore
            "a'b'c'",
            'a"b"c"',
            # Technically HTML parsing errors, but are ok since these won't lead
            # to a loss of content when parsed.
            "a<5",
            "a < b",
            "a <ä",
            "a <ä>",
            "a <",
            "a&",
            "a&*",
            "a&5",
            "a & b",
            "a&b",
            "c&#b",
            "number <span>1<2</span> ok",
            "go <em>a&b</em>",
            "<img val='a&b'>",
            # With fluent references.
            "<a data-val='ok'>{ $var }</a>",
            "space < { $var }",
            "space & { $var }",
            # Allowed in an attribute, although not expected and not safe
            # practice.
            "<a data-val='{ message }'>a { -term }</a> and { $var }",
            # With literals. These are expanded before testing.
            'a { "<span>" } ok </span>',
            'a &{ "eth" }; ok',
            # \" in fluent string literal is expanded to just ".
            'a { "<span data-val=\\"val\\">" } ok </span>',
            # With unicode escaped in fluent string literal.
            'a { "\\u003Cspan\\u003e" } ok </span{ "\\U00003e" }',
            '{ "a \\U000026et" }h; ok',
            # Invalid unicode doesn't cause HTML validator to throw.
            '{ "my\\UFFFFFFbad unicode" }',
            # Normally <{ or &{ is not allowed because it might expand into a
            # fluent reference, but a literal "{" is ok.
            'a<{ "{" }b',
            'a{ "<{b" }c',
            'a&{ "{" }b',
            'a{ "&{b" }c',
            # With variants, each variant is parsed individually.
            "<p>add ${ $n ->\n  [one] { $n } tab\n *[other] { $n } tabs\n}</p>",
            # Need not match.
            "<p>add ${ $n ->\n"
            "  [one] { $n } tab <br> more\n"
            " *[other] { $n } tabs\n"
            "}</p>",
            "<p>add ${ $n ->\n"
            "  [one] { $n } tab <br> more\n"
            " *[other] { $n } tabs\n"
            "} and ${ $var ->\n"
            "  [yes] <img>\n"
            " *[no] none\n"
            "}</p>",
            "<p>add ${ PLATFORM() ->\n"
            "  [linux] tab </p>\n"
            "  [macos] <em data-var='ok'>{ -term }</em> tabs </p>\n"
            " *[other] { $n } <br> tabs </p>\n"
            "}",
        ):
            for fluent_type in ("Message", "Term"):
                self.assert_html_ok(value, fluent_type)
                # With an attribute.
                self.assert_html_ok(f"{value}\n.attr = ok", fluent_type)
                # Attribute need not be valid inner HTML.
                self.assert_html_ok(f"{value}\n.attr = a<img", fluent_type)

    def test_html_errors(self) -> None:
        for fluent_type in ("Message", "Term"):
            self.assert_html_error(
                "a<{ $var }",
                fluent_type,
                "The Fluent reference in <code>&lt;{ $var }</code> may expand "
                "into a HTML tag. Maybe use <code>&amp;lt;{ $var }</code>.",
            )
            self.assert_html_error(
                'before <span>a<{ -term(param: 5, p2: "yes") }b</span> after',
                fluent_type,
                "The Fluent reference in "
                '<code>&lt;{ -term(param: 5, p2: "yes") }</code> '
                "may expand into a HTML tag. Maybe use "
                '<code>&amp;lt;{ -term(param: 5, p2: "yes") }</code>.',
            )
            # Putting the "<" in a literal will not help.
            self.assert_html_error(
                'a { "<" }{ $var }',
                fluent_type,
                "The Fluent reference in <code>&lt;{ $var }</code> may expand "
                "into a HTML tag. Maybe use <code>&amp;lt;{ $var }</code>.",
            )
            # Even unicode escape for "<".
            self.assert_html_error(
                '{ "a \\u003c" }{ $var }',
                fluent_type,
                "The Fluent reference in <code>&lt;{ $var }</code> may expand "
                "into a HTML tag. Maybe use <code>&amp;lt;{ $var }</code>.",
            )
            self.assert_html_error(
                'a { "\\U00003C" }{ $var }',
                fluent_type,
                "The Fluent reference in <code>&lt;{ $var }</code> may expand "
                "into a HTML tag. Maybe use <code>&amp;lt;{ $var }</code>.",
            )
            self.assert_html_error(
                "a&{ FUNC($var) }",
                fluent_type,
                "The Fluent reference in <code>&amp;{ FUNC($var) }</code> may "
                "expand into a HTML character reference. Maybe use "
                "<code>&amp;amp;{ FUNC($var) }</code>.",
            )
            self.assert_html_error(
                "before <p data-val='&{ -term }'>x</p>",
                fluent_type,
                "The Fluent reference in <code>&amp;{ -term }</code> may "
                "expand into a HTML character reference. Maybe use "
                "<code>&amp;amp;{ -term }</code>.",
            )

            # Not allowed comments, CDATA, processing instructions, etc.
            self.assert_html_error(
                "add <!--comment-->",
                fluent_type,
                "Fluent inner HTML should not include <code>&lt;!</code>. "
                "Maybe use <code>&amp;lt;!</code>.",
            )
            self.assert_html_error(
                "add <span><!--comment--></span>",
                fluent_type,
                "Fluent inner HTML should not include <code>&lt;!</code>. "
                "Maybe use <code>&amp;lt;!</code>.",
            )
            self.assert_html_error(
                "add <!comment>",
                fluent_type,
                "Fluent inner HTML should not include <code>&lt;!</code>. "
                "Maybe use <code>&amp;lt;!</code>.",
            )
            self.assert_html_error(
                "<!DOCTYPE html>",
                fluent_type,
                "Fluent inner HTML should not include <code>&lt;!</code>. "
                "Maybe use <code>&amp;lt;!</code>.",
            )
            self.assert_html_error(
                "<![CDATA[x<y]]>",
                fluent_type,
                "Fluent inner HTML should not include <code>&lt;!</code>. "
                "Maybe use <code>&amp;lt;!</code>.",
            )
            self.assert_html_error(
                "a <?xml-stylesheet type='text/css' href='.'>",
                fluent_type,
                "Fluent inner HTML should not include <code>&lt;?</code>. "
                "Maybe use <code>&amp;lt;?</code>.",
            )

            # Invalid end tags.
            self.assert_html_error(
                "<span>hello</ span>",
                fluent_type,
                "The sequence <code>&lt;/</code> begins with a HTML closing tag, "
                "but the name or syntax is not valid. If you do not want a "
                "closing tag, use <code>&amp;lt;/</code>.",
            )
            self.assert_html_error(
                "hello</>",
                fluent_type,
                "The sequence <code>&lt;/</code> begins with a HTML closing tag, "
                "but the name or syntax is not valid. If you do not want a "
                "closing tag, use <code>&amp;lt;/</code>.",
            )
            self.assert_html_error(
                "hello</",
                fluent_type,
                "The sequence <code>&lt;/</code> begins with a HTML closing tag, "
                "but the name or syntax is not valid. If you do not want a "
                "closing tag, use <code>&amp;lt;/</code>.",
            )
            self.assert_html_error(
                "<span>hello</span",
                fluent_type,
                "The sequence <code>&lt;/span</code> begins with a HTML closing tag, "
                "but the name or syntax is not valid. If you do not want a "
                "closing tag, use <code>&amp;lt;/span</code>.",
            )
            self.assert_html_error(
                "<span>hello</span hidden=''>",
                fluent_type,
                "The sequence <code>&lt;/span</code> begins with a HTML closing tag, "
                "but the name or syntax is not valid. If you do not want a "
                "closing tag, use <code>&amp;lt;/span</code>.",
            )
            self.assert_html_error(
                "<span>hello</5>",
                fluent_type,
                "The sequence <code>&lt;/5</code> begins with a HTML closing tag, "
                "but the name or syntax is not valid. If you do not want a "
                "closing tag, use <code>&amp;lt;/5</code>.",
            )
            self.assert_html_error(
                "<span>hello</sp~n>",
                fluent_type,
                "The sequence <code>&lt;/sp~n</code> begins with a HTML closing tag, "
                "but the name or syntax is not valid. If you do not want a "
                "closing tag, use <code>&amp;lt;/sp~n</code>.",
            )

            # Invalid start tag names.
            self.assert_html_error(
                "a <sp~n and",
                fluent_type,
                "The sequence <code>&lt;sp~n</code> begins with a HTML tag, "
                "but the name is not valid. If you do not want to begin a HTML "
                "tag, use <code>&amp;lt;sp~n</code>.",
            )
            # Fluent literal does not help.
            self.assert_html_error(
                'a { "<" }sp~n and',
                fluent_type,
                "The sequence <code>&lt;sp~n</code> begins with a HTML tag, "
                "but the name is not valid. If you do not want to begin a HTML "
                "tag, use <code>&amp;lt;sp~n</code>.",
            )
            self.assert_html_error(
                "a <sp~n> and </sp~n>",
                fluent_type,
                "The sequence <code>&lt;sp~n</code> begins with a HTML tag, "
                "but the name is not valid. If you do not want to begin a HTML "
                "tag, use <code>&amp;lt;sp~n</code>.",
            )
            # Technically an allowed custom name, but not allowed by our parser
            # to keep it simple.
            self.assert_html_error(
                "a <my-😄> and </my-😄>",
                fluent_type,
                "The sequence <code>&lt;my-😄</code> begins with a HTML tag, "
                "but the name is not valid. If you do not want to begin a HTML "
                "tag, use <code>&amp;lt;my-😄</code>.",
            )

            # Start tag is not closed.
            self.assert_html_error(
                "a <div",
                fluent_type,
                "The sequence <code>&lt;div</code> begins with a HTML tag, "
                "but the tag is never closed by <code>></code>. If you do not "
                "want to begin a HTML tag, use <code>&amp;lt;div</code>.",
            )
            self.assert_html_error(
                "a <div data-val=''",
                fluent_type,
                "The sequence <code>&lt;div</code> begins with a HTML tag, "
                "but the tag is never closed by <code>></code>. If you do not "
                "want to begin a HTML tag, use <code>&amp;lt;div</code>.",
            )
            self.assert_html_error(
                "a <img data-val='a' \n\t",
                fluent_type,
                "The sequence <code>&lt;img</code> begins with a HTML tag, "
                "but the tag is never closed by <code>></code>. If you do not "
                "want to begin a HTML tag, use <code>&amp;lt;img</code>.",
            )

            # Invalid attribute, with no equal sign.
            self.assert_html_error(
                "a <span attr",
                fluent_type,
                "The sequence <code>&lt;span</code> begins with a HTML tag, "
                "but the sequence <code>attr</code> is not a valid attribute "
                "with a value. If you do not want to begin a HTML tag, use "
                "<code>&amp;lt;span</code>.",
            )
            self.assert_html_error(
                "a <span class='val' attr and more",
                fluent_type,
                "The sequence <code>&lt;span</code> begins with a HTML tag, "
                "but the sequence <code>attr</code> is not a valid attribute "
                "with a value. If you do not want to begin a HTML tag, use "
                "<code>&amp;lt;span</code>.",
            )
            self.assert_html_error(
                "a <p><em att*va>content</em></p>",
                fluent_type,
                "The sequence <code>&lt;em</code> begins with a HTML tag, "
                "but the sequence <code>att*va</code> is not a valid attribute "
                "with a value. If you do not want to begin a HTML tag, use "
                "<code>&amp;lt;em</code>.",
            )
            # Attribute with no value.
            self.assert_html_error(
                "a <p><img attr></p>",
                fluent_type,
                "The sequence <code>&lt;img</code> begins with a HTML tag, "
                "but the sequence <code>attr</code> is not a valid attribute "
                "with a value. If you do not want to begin a HTML tag, use "
                "<code>&amp;lt;img</code>.",
            )

            # Invalid attribute name with an equal sign.
            self.assert_html_error(
                "a <div 3='ok'>content</div>",
                fluent_type,
                "The HTML attribute name <code>3</code> for the "
                "<code>&lt;div&gt;</code> tag is not valid.",
            )
            self.assert_html_error(
                "<div a+a='ok'>content</div>",
                fluent_type,
                "The HTML attribute name <code>a+a</code> for the "
                "<code>&lt;div&gt;</code> tag is not valid.",
            )

            # Invalid attribute value.
            self.assert_html_error(
                "add <img class=val >",
                fluent_type,
                "The HTML <code>class</code> attribute value "
                "<code>val</code> for the <code>&lt;img&gt;</code> "
                "tag is not a valid quoted value.",
            )
            self.assert_html_error(
                "add <strong class='val1 val2' attr='hello'a>a</strong>",
                fluent_type,
                "The HTML <code>attr</code> attribute value "
                "<code>'hello'a</code> for the <code>&lt;strong&gt;</code> "
                "tag is not a valid quoted value.",
            )
            self.assert_html_error(
                'add <strong class="a"b">a</strong>',
                fluent_type,
                "The HTML <code>class</code> attribute value "
                '<code>"a"b"</code> for the <code>&lt;strong&gt;</code> '
                "tag is not a valid quoted value.",
            )
            self.assert_html_error(
                '<wbr class="a"data-val="" />',
                fluent_type,
                "The HTML <code>class</code> attribute value "
                '<code>"a"data-val=""</code> for the <code>&lt;wbr&gt;</code> '
                "tag is not a valid quoted value.",
            )

            # Double attribute names.
            self.assert_html_error(
                "<main class=\"ok\" data-val='ok' class='other'>content</main>",
                fluent_type,
                "The HTML <code>class</code> attribute appears twice for "
                "the <code>&lt;main&gt;</code> tag.",
            )

            # Unmatched end tag.
            self.assert_html_error(
                "add </div>",
                fluent_type,
                "Unmatched HTML end tag: <code>&lt;/div&gt;</code>.",
            )
            self.assert_html_error(
                "add <p>string</span></p>",
                fluent_type,
                "Unmatched HTML end tag: <code>&lt;/span&gt;</code>.",
            )
            self.assert_html_error(
                "add <span><p>string</span></p>",
                fluent_type,
                "Unmatched HTML end tag: <code>&lt;/span&gt;</code>.",
            )
            # Different cases do not count as a match.
            self.assert_html_error(
                "add <span>string</SPAN>",
                fluent_type,
                "Unmatched HTML end tag: <code>&lt;/SPAN&gt;</code>.",
            )
            self.assert_html_error(
                "add <SPAN>string</sPAN>",
                fluent_type,
                "Unmatched HTML end tag: <code>&lt;/sPAN&gt;</code>.",
            )

            # End tag for a void element.
            self.assert_html_error(
                "hello<br>and</br>",
                fluent_type,
                "The HTML <code>br</code> void element should not have an end "
                "tag: <code>&lt;/br&gt;</code>.",
            )
            self.assert_html_error(
                "hello<img></img>",
                fluent_type,
                "The HTML <code>img</code> void element should not have an end "
                "tag: <code>&lt;/img&gt;</code>.",
            )

            # Self-closing a non-void element.
            self.assert_html_error(
                "a <span/> closed",
                fluent_type,
                "The HTML <code>span</code> element is not a known void "
                "element, so should not have a self-closing tag: "
                "<code>&lt;span/&gt;</code>.",
            )
            self.assert_html_error(
                "a <custom-el attr='ok'/> closed",
                fluent_type,
                "The HTML <code>custom-el</code> element is not a known void "
                "element, so should not have a self-closing tag: "
                "<code>&lt;custom-el/&gt;</code>.",
            )

            # Tag not closed.
            self.assert_html_error(
                "open <span>a tag",
                fluent_type,
                "The HTML <code>&lt;span&gt;</code> tag is missing a "
                "matching end tag: <code>&lt;/span&gt;</code>.",
            )
            self.assert_html_error(
                "<p>open <span data-val='ok'>a tag <em>",
                fluent_type,
                "The HTML <code>&lt;p&gt;</code> tag is missing a "
                "matching end tag: <code>&lt;/p&gt;</code>.",
            )

            # Accidental character references.
            self.assert_html_error(
                "nice&ethical",
                fluent_type,
                "The sequence <code>&amp;ethical</code> will begin a HTML "
                "character reference, but does not end with "
                "<code>;</code>. If you do not want a character reference, "
                "use <code>&amp;amp;ethical</code>.",
            )
            self.assert_html_error(
                "<p>character &#90</p>",
                fluent_type,
                "The sequence <code>&amp;#90</code> will begin a HTML "
                "character reference, but does not end with "
                "<code>;</code>. If you do not want a character reference, "
                "use <code>&amp;amp;#90</code>.",
            )
            self.assert_html_error(
                "<p class='a&gt~hello'>content</p>",
                fluent_type,
                "The sequence <code>&amp;gt</code> will begin a HTML "
                "character reference, but does not end with "
                "<code>;</code>. If you do not want a character reference, "
                "use <code>&amp;amp;gt</code>.",
            )

            # Explicit character reference that does not expand.
            self.assert_html_error(
                "&oth;",
                fluent_type,
                "The sequence <code>&amp;oth;</code> is not a valid HTML "
                "character reference.",
            )
            self.assert_html_error(
                # "&ampe;" would expand to "&e;".
                "<div>Add &ampe;more</div>",
                fluent_type,
                "The sequence <code>&amp;ampe;</code> is not a valid HTML "
                "character reference.",
            )
            self.assert_html_error(
                '<div class="a&#xabg;b">content</div>',
                fluent_type,
                "The sequence <code>&amp;#xabg;</code> is not a valid HTML "
                "character reference.",
            )
            self.assert_html_error(
                "content&#09a;more",
                fluent_type,
                "The sequence <code>&amp;#09a;</code> is not a valid HTML "
                "character reference.",
            )

            # Some errors with variants.
            self.assert_html_error(
                "{ $var ->\n  [one] <span>open\n *[other] none\n} close</span>",
                fluent_type,
                "Unmatched HTML end tag: <code>&lt;/span&gt;</code>.",
            )
            self.assert_html_error(
                "{ FUNC($var, $num) ->\n"
                "  [equal] same\n"
                "  [greater] { $var }>{ $num }\n"
                " *[less] { $var }<{ $num }\n"
                "}",
                fluent_type,
                "The Fluent reference in <code>&lt;{ $num }</code> may expand "
                "into a HTML tag. Maybe use <code>&amp;lt;{ $num }</code>.",
            )
            self.assert_html_error(
                "a <{ $var ->\n  [zero] none\n *[other] { $var }\n}",
                fluent_type,
                "The sequence <code>&lt;none</code> begins with a HTML tag, "
                "but the tag is never closed by <code>></code>. If you do not "
                "want to begin a HTML tag, use <code>&amp;lt;none</code>.",
            )


class FluentSourceInnerHTMLCheckTest(FluentCheckTestBase, FluentInnerHTMLCheckTestBase):
    check = FluentSourceInnerHTMLCheck()
    syntax_check = FluentSourceSyntaxCheck()

    def assert_html_ok(self, value: str, fluent_type: str) -> None:
        self.assert_source_check_passes(self.check, value, fluent_type)
        # Ensure the syntax is ok.
        self.assert_source_check_passes(self.syntax_check, value, fluent_type)

    def assert_html_error(
        self,
        value: str,
        fluent_type: str,
        description: str,
    ) -> None:
        self.assert_source_check_fails(self.check, value, fluent_type, description)
        # Ensure the syntax is ok.
        self.assert_source_check_passes(self.syntax_check, value, fluent_type)


class FluentTargetInnerHTMLCheckTest(FluentCheckTestBase, FluentInnerHTMLCheckTestBase):
    check = FluentTargetInnerHTMLCheck()
    syntax_check = FluentTargetSyntaxCheck()

    def assert_html_ok(self, value: str, fluent_type: str) -> None:
        # Check is independent of the source value, but we want the structures
        # to match to not raise non-syntax errors, so make the source the same
        # as the target.
        self.assert_target_check_passes(self.check, value, value, fluent_type)
        # Ensure the syntax is ok.
        self.assert_target_check_passes(self.syntax_check, "ok", value, fluent_type)

    def assert_html_error(
        self,
        value: str,
        fluent_type: str,
        description: str,
    ) -> None:
        # HTML structure does not need to match since we expect a parsing error.
        self.assert_target_check_fails(
            self.check, "ok", value, fluent_type, description
        )
        # Ensure the syntax is ok.
        self.assert_target_check_passes(self.syntax_check, "ok", value, fluent_type)

    def test_same_inner_html(self) -> None:
        for matching_sources in (
            ("source1", "source2"),
            ("a<span>ok</span>", "<span>fine</span>b"),
            ("and <img>", "<img > and", "self <img/> close"),
            (
                # Re-ordering is ok.
                "<h1>heading</h1><p>some<br><i>para</i></p>",
                "<p><i>some</i>para<br></p>content<h1>heading</h1>",
            ),
            # With matching attributes.
            (
                "some <span data-val1='ok' data-val2='no'>text</span>",
                "some <span\tdata-val1='ok'\n data-val2='no' \t>text</span>",
                "some <span data-val2=\"no\" data-val1='ok'>text</span>",
            ),
            # With fluent string literals.
            (
                "some <span data-val2='no'>text</span>",
                'so{ "me \\u003Cspan data-val2=\\"no\\"> text" }</span>',
            ),
            # With same element appearing twice.
            (
                "<p>first<br>second<br>third</p>",
                "<p>a<br>b<br />c</p>",
            ),
            # With selectors.
            (
                "<p>a<i>{ $num }</i>c and <img data-val='ok'></p>",
                "<p>{ $num ->\n"
                "  [zero] <i>none</i>\n"
                " *[other] <i>{ $num }</i>\n"
                "} and <img data-val='ok' ></p>",
                "<p>{ $num ->\n"
                '  [zero] <img data-val="ok"/> <i>none</i></p>\n'
                " *[other] <i>{ $num }</i> and <img data-val='ok'></p>\n"
                "}",
                "<p> <i>{ $num ->\n"
                "  [zero] none\n"
                "  [one] one\n"
                " *[other] { $num }\n"
                "}</i> and { FUNC() ->\n"
                "  [a] a <img data-val='ok'></p>\n"
                " *[b] b <img data-val='ok'></p>\n"
                "}",
            ),
            # With selectors with different elements in each variant.
            (
                "{ FUNC() ->\n"
                "  [yes] <img data-val1='yes' data-val2='y'> and <br>\n"
                " *[no] <img data-val1='no'> and <br> and <i>more</i>\n"
                "}",
                "<img { FUNC() ->\n"
                "  [yes] data-val1='yes' data-val2='y'>\n"
                " *[no] data-val1='no'> and <i>more</i>\n"
                "} and <br>",
            ),
            (
                "<p>{ $var ->\n"
                "  [b] add <b>tag</b>\n"
                " *[i] add <i data-val='some val'>tag</i>\n"
                "  [strong] add <strong>t<br>ag</strong>\n"
                "}</p>",
                "<p>{ FUNC($var) ->\n"
                "  [x] add <b>tag</b>\n"
                "  [i] add <i data-val='some val'>tag</i>\n"
                "  [strong] <strong><br></strong>\n"
                " *[y] add <b>tags</b>\n"
                "}</p>",
                "{ FUNC($var) ->\n"
                "  [x] <p> add <b>tag</b>\n"
                "  [i] <p>add <i data-val='some val'>tag</i> more\n"
                " *[strong] <p>{ $var ->\n"
                "    [a] <strong><br></strong>\n"
                "   *[b] <strong>before<br>after</strong>\n"
                "  }\n"
                "}</p>",
            ),
        ):
            # The check should be transitive and symmetric, so the check should
            # pass for all pairs compared against each other.
            for source, target in itertools.permutations(matching_sources, 2):
                self.assert_checks(source, target, "Term")
                self.assert_checks(source, target, "Message")

    def test_different_inner_html(self) -> None:
        for fluent_type in ("Message", "Term"):
            self.assert_target_check_fails(
                self.check,
                "<strong>source</strong>",
                "target",
                fluent_type,
                "Fluent value is missing a HTML "
                "<code>&lt;strong&gt;…&lt;/strong&gt;</code> tag.",
            )
            self.assert_target_check_fails(
                self.check,
                "<em>source</em>\n.title = text",
                "target\n.title = <em>text</em>",
                fluent_type,
                "Fluent value is missing a HTML "
                "<code>&lt;em&gt;…&lt;/em&gt;</code> tag.",
            )
            # For void elements, the tag is serialized as self-closing.
            self.assert_target_check_fails(
                self.check,
                "with <img/>",
                "target",
                fluent_type,
                "Fluent value is missing a HTML <code>&lt;img/&gt;</code> tag.",
            )
            self.assert_target_check_fails(
                self.check,
                "with <br>",
                "target",
                fluent_type,
                "Fluent value is missing a HTML <code>&lt;br/&gt;</code> tag.",
            )
            # With attribute.
            self.assert_target_check_fails(
                self.check,
                "with <a data-val='ok'>text</a>",
                "target",
                fluent_type,
                "Fluent value is missing a HTML "
                '<code>&lt;a data-val="ok"&gt;…&lt;/a&gt;</code> tag.',
            )
            # When attribute value contains a double-quote, the serialized tag
            # uses a single quote.
            self.assert_target_check_fails(
                self.check,
                "with <a data-val='ok\"' class='other'>text</a>",
                "target",
                fluent_type,
                "Fluent value is missing a HTML "
                '<code>&lt;a data-val=\'ok"\' class="other"&gt;'
                "…&lt;/a&gt;</code> tag.",
            )

            # Extra elements.
            self.assert_target_check_fails(
                self.check,
                "none",
                "target <img> more",
                fluent_type,
                "Fluent value has an unexpected extra HTML "
                "<code>&lt;img/&gt;</code> tag.",
            )

            # Different counts.
            self.assert_target_check_fails(
                self.check,
                "source<br>has<br>two",
                "target<br>one",
                fluent_type,
                "Fluent value is missing a HTML <code>&lt;br/&gt;</code> tag.",
            )
            self.assert_target_check_fails(
                self.check,
                "<i>source</i><br/>has<br/>two",
                "<br/>target<br><i>has</i><br/>four<br>",
                fluent_type,
                "Fluent value has an unexpected extra HTML "
                "<code>&lt;br/&gt;</code> tag.",
            )

            # Both missing and extra.
            self.assert_target_check_fails(
                self.check,
                "<i>source</i> <img>",
                "<img> <em data-val='ok'>target</em> val",
                fluent_type,
                "Fluent value is missing a HTML "
                "<code>&lt;i&gt;…&lt;/i&gt;</code> tag.<br>"
                "Fluent value has an unexpected extra HTML "
                '<code>&lt;em data-val="ok"&gt;…&lt;/em&gt;</code> tag.',
            )

            # Sub-element is missing.
            self.assert_target_check_fails(
                self.check,
                "<p>first<br>expected</p>",
                "<p>missing br</p>",
                fluent_type,
                "Fluent value is missing a HTML "
                "<code>&lt;p&gt;&lt;br/&gt;&lt;/p&gt;</code> tag.",
            )
            self.assert_target_check_fails(
                self.check,
                "<p>first<br>expected</p>",
                "<p>missing <i>a<br>b</i></p>",
                fluent_type,
                "Fluent value is missing a HTML "
                "<code>&lt;p&gt;&lt;br/&gt;&lt;/p&gt;</code> tag.<br>"
                "Fluent value has an unexpected extra HTML "
                "<code>&lt;p&gt;&lt;i&gt;…&lt;/i&gt;&lt;/p&gt;</code> tag.<br>"
                "Fluent value has an unexpected extra HTML "
                "<code>&lt;p&gt;&lt;i&gt;"
                "&lt;br/&gt;&lt;/i&gt;&lt;/p&gt;</code> tag.",
            )
            # Element with a different parent does not count.
            self.assert_target_check_fails(
                self.check,
                "add <p>with<img></p>",
                "<p>with</p> <img>",
                fluent_type,
                "Fluent value is missing a HTML "
                "<code>&lt;p&gt;&lt;img/&gt;&lt;/p&gt;</code> tag.<br>"
                "Fluent value has an unexpected extra HTML "
                "<code>&lt;img/&gt;</code> tag.",
            )
            self.assert_target_check_fails(
                self.check,
                "<em>first</em> and <strong>second</strong>",
                "<em>first and <strong>second</strong></em>",
                fluent_type,
                "Fluent value is missing a HTML "
                "<code>&lt;strong&gt;…&lt;/strong&gt;</code> tag.<br>"
                "Fluent value has an unexpected extra HTML "
                "<code>&lt;em&gt;&lt;strong&gt;"
                "…&lt;/strong&gt;&lt;/em&gt;</code> tag.",
            )

            # Tags with different attributes do not match.
            self.assert_target_check_fails(
                self.check,
                "<span data-val='ok'>text</span> more",
                "<span>text</span> more",
                fluent_type,
                "Fluent value is missing a HTML "
                '<code>&lt;span data-val="ok"&gt;…&lt;/span&gt;</code> tag.<br>'
                "Fluent value has an unexpected extra HTML "
                "<code>&lt;span&gt;…&lt;/span&gt;</code> tag.",
            )
            self.assert_target_check_fails(
                self.check,
                "<span data-val='ok'>text</span> more",
                "<span data-val='not'>text</span> more",
                fluent_type,
                "Fluent value is missing a HTML "
                '<code>&lt;span data-val="ok"&gt;…&lt;/span&gt;</code> tag.<br>'
                "Fluent value has an unexpected extra HTML "
                '<code>&lt;span data-val="not"&gt;…&lt;/span&gt;</code> tag.',
            )

            # Tags with different case do not match.
            self.assert_target_check_fails(
                self.check,
                "<SPAN>text</SPAN> more",
                "<span>text</span> more",
                fluent_type,
                "Fluent value is missing a HTML "
                "<code>&lt;SPAN&gt;…&lt;/SPAN&gt;</code> tag.<br>"
                "Fluent value has an unexpected extra HTML "
                "<code>&lt;span&gt;…&lt;/span&gt;</code> tag.",
            )

            # With selectors in the source that all have the same tags.
            for source in (
                # Equivalent sources.
                "<p class='ok'><span data-val='a'>first</span><br>"
                "<span data-val='b'>second</span></p>",
                "<p class='ok'>{ FUNC() ->\n"
                "  [a] <span data-val='a'>a</span><br>"
                "<span data-val='b'>b</span>\n"
                " *[b] <span data-val='b'>B</span><br>"
                "<span data-val='a'>A</span>\n"
                "}</p>",
                '<p class="ok"><span data-val="a"></span><br>{ $var ->\n'
                "  [1] <span data-val='b'>one</span></p>\n"
                "  [2] <span data-val='b'>two</span></p>\n"
                " *[3] <span data-val='b'>three</span></p>\n"
                "}",
            ):
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "<p class='ok'>"
                    "<span data-val='a'>first</span><br>"
                    '<span data-val="a">second</span></p>',
                    fluent_type,
                    "Fluent value is missing a HTML "
                    '<code>&lt;p class="ok"&gt;&lt;span data-val="b"&gt;'
                    "…&lt;/span&gt;&lt;/p&gt;</code> tag.<br>"
                    "Fluent value has an unexpected extra HTML "
                    '<code>&lt;p class="ok"&gt;&lt;span data-val="a"&gt;'
                    "…&lt;/span&gt;&lt;/p&gt;</code> tag.",
                )
                # With multiple variants, and each has the same problem.
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "<p class='ok'><span data-val='a'>ok</span>{ $var ->\n"
                    "  [yes] b\n"
                    " *[no] c\n"
                    "} and { FUNC() -> \n"
                    "  [a] <span data-val='b'>A</span>\n"
                    " *[b] <span data-val='b'>B</span>\n"
                    "}</p> and <img>",
                    fluent_type,
                    "Fluent value is missing a HTML "
                    '<code>&lt;p class="ok"&gt;&lt;br/&gt;&lt;/p&gt;</code> '
                    "tag.<br>Fluent value has an unexpected extra HTML "
                    "<code>&lt;img/&gt;</code> tag.",
                )
                # Only some of the variants have a problem.
                self.assert_target_check_fails(
                    self.check,
                    source,
                    "<p class='ok'><span data-val='a'>ok</span>{ $var ->\n"
                    "  [yes] b <br>\n"
                    " *[no] c\n"
                    "} and { FUNC() ->\n"
                    "  [a] <span data-val='b'>A</span>with<br>\n"
                    "  [b] <span data-val='b'>B</span>\n"
                    " *[c] <span data-val='b'>C</span>\n"
                    "}</p>",
                    fluent_type,
                    "Fluent value is missing a HTML "
                    '<code>&lt;p class="ok"&gt;&lt;br/&gt;&lt;/p&gt;</code> '
                    "tag for the following variants: "
                    "<code>[no][b], [no][c]</code>.<br>"
                    "Fluent value has an unexpected extra HTML "
                    '<code>&lt;p class="ok"&gt;&lt;br/&gt;&lt;/p&gt;</code> '
                    "tag for the following variants: <code>[yes][a]</code>.",
                )

            # When the source has variants with different nodes the message is
            # more generic.
            self.assert_target_check_fails(
                self.check,
                "add { $var ->\n"
                "  [yes] <a data-val='ok'>text</a>\n"
                " *[no] no\n"
                "} with <wbr> { PLATFORM() ->\n"
                "  [linux] a <strong>{ -term }</strong>\n"
                " *[other] <em>nothing</em>\n"
                "}",
                "nothing <wbr><em>nothing</em>",
                fluent_type,
                "The following variants in the original Fluent value do not "
                "have at least one matching variant in the translation with "
                "the same set of HTML elements: <code>[yes][linux], "
                "[no][linux], [yes][other]</code>.",
            )
            self.assert_target_check_fails(
                self.check,
                "{ PLATFORM() ->\n  [yes] <a data-val='ok'>text</a>\n *[no] none\n}",
                "<a data-val='not'>text</a>",
                fluent_type,
                "The following variants in the original Fluent value do not "
                "have at least one matching variant in the translation with "
                "the same set of HTML elements: <code>[yes], [no]</code>.<br>"
                "The translated Fluent value does not have a matching variant "
                "in the original with the same set of HTML elements.",
            )
            self.assert_target_check_fails(
                self.check,
                "{ $var ->\n"
                "  [a] <i>string</i> and <img data-val='ok'>\n"
                " *[b] <b>string</b>\n"
                "}",
                "{ $var ->\n"
                "  [a] <i>string</i>\n"
                " *[b] <b>string</b>\n"
                "} and { FUNC() ->\n"
                "  [YES] <img data-val='ok'>\n"
                " *[NO] none\n"
                "}",
                fluent_type,
                "The following variants in the translated Fluent "
                "value do not have a matching variant in "
                "the original with the same set of HTML elements: "
                "<code>[b][YES], [a][NO]</code>.",
            )
            self.assert_target_check_fails(
                self.check,
                "{ $var ->\n"
                "  [a] <i>string</i> and <img data-val='ok'>\n"
                " *[b] <b>string</b>\n"
                "}",
                "{ $var ->\n"
                "  [a] <i>string</i>\n"
                " *[b] <b>string</b>\n"
                "} and { FUNC() ->\n"
                "  [YES] <img data-val='not'>\n"
                " *[NO] none\n"
                "}",
                fluent_type,
                "The following variants in the original Fluent value do not "
                "have at least one matching variant in the translation with "
                "the same set of HTML elements: <code>[a]</code>.<br>"
                "The following variants in the translated Fluent "
                "value do not have a matching variant in "
                "the original with the same set of HTML elements: "
                "<code>[a][YES], [b][YES], [a][NO]</code>.",
            )

    def test_with_invalid_source(self) -> None:
        for fluent_type in ("Message", "Term"):
            # If the source could not be parsed, then the target will only need
            # to parse to pass the check.
            self.assert_checks(
                "<span>source</SPAN>",
                "<span>target</span>",
                fluent_type,
                {
                    FluentSourceInnerHTMLCheck: False,
                    FluentTargetInnerHTMLCheck: True,
                },
            )
            self.assert_checks(
                "<span hidden>source</span>",
                "<em>target</em>",
                fluent_type,
                {
                    FluentSourceInnerHTMLCheck: False,
                    FluentTargetInnerHTMLCheck: True,
                },
            )
            # If both are invalid, both fail.
            self.assert_checks(
                "<span hidden>source</span>",
                "<em hidden>target</em>",
                fluent_type,
                {
                    FluentSourceInnerHTMLCheck: False,
                    FluentTargetInnerHTMLCheck: False,
                },
            )

    def test_missing_value(self) -> None:
        # If we are missing the value in the target or source, we get a parts
        # error, but no comparison error for the HTML.
        self.assert_checks(
            ".title = ok",
            "value\n.title = ok",
            "Message",
            {
                FluentPartsCheck: False,
                FluentSourceInnerHTMLCheck: True,
                FluentTargetInnerHTMLCheck: True,
            },
        )
        self.assert_checks(
            "value\n.title = ok",
            ".title = ok",
            "Message",
            {
                FluentPartsCheck: False,
                FluentSourceInnerHTMLCheck: True,
                FluentTargetInnerHTMLCheck: True,
            },
        )
        self.assert_checks(
            ".title = ok",
            "value <img>\n.title = ok",
            "Message",
            {
                FluentPartsCheck: False,
                FluentSourceInnerHTMLCheck: True,
                FluentTargetInnerHTMLCheck: True,
            },
        )
        self.assert_checks(
            "<i>hello</i>.title = ok",
            ".title = ok",
            "Message",
            {
                FluentPartsCheck: False,
                FluentSourceInnerHTMLCheck: True,
                FluentTargetInnerHTMLCheck: True,
            },
        )
        # Still get HTML error if cannot parse.
        self.assert_checks(
            ".title = ok",
            "value <img\n.title = ok",
            "Message",
            {
                FluentPartsCheck: False,
                FluentSourceInnerHTMLCheck: True,
                FluentTargetInnerHTMLCheck: False,
            },
        )
        self.assert_checks(
            "<hello>.title = ok",
            ".title = ok",
            "Message",
            {
                FluentPartsCheck: False,
                FluentSourceInnerHTMLCheck: False,
                FluentTargetInnerHTMLCheck: True,
            },
        )

    def test_with_syntax_error(self) -> None:
        # If there is a syntax error in the source or target, we do not get a
        # html error.
        for source, source_ok, target, target_ok in (
            (
                "<sp~n { -term.attr }",
                False,
                "<span>ok</span>",
                True,
            ),
            (
                "<{ $var",
                False,
                "<img {",
                False,
            ),
            (
                "<span alt='quote'>val</span>\n.attr = ok",
                True,
                "<span alt=noquote></span>\n.attr =",
                False,
            ),
        ):
            for fluent_type in ("Message", "Term"):
                self.assert_checks(
                    source,
                    target,
                    fluent_type,
                    {
                        FluentSourceInnerHTMLCheck: True,
                        FluentTargetInnerHTMLCheck: True,
                        FluentSourceSyntaxCheck: source_ok,
                        FluentTargetSyntaxCheck: target_ok,
                    },
                )

    def test_html_highlight(self) -> None:
        for fluent_type in ("Term", "Message"):
            self.assert_source_highlights(self.check, "source", fluent_type, [])
            self.assert_source_highlights(
                self.check,
                "my <img/> tag",
                fluent_type,
                [(3, "<img/>")],
            )
            self.assert_source_highlights(
                self.check,
                "a <br> and <br /> tag",
                fluent_type,
                [(2, "<br>"), (11, "<br />")],
            )
            self.assert_source_highlights(
                self.check,
                "a <em data-val='ok'>text</em> after",
                fluent_type,
                [(2, "<em data-val='ok'>"), (24, "</em>")],
            )
            self.assert_source_highlights(
                self.check,
                'ab <p\tclass="c1 c2" >&lt;<i a=\'ok\' b="+"\n>text</i></p> after',
                fluent_type,
                [
                    (3, '<p\tclass="c1 c2" >'),
                    (25, "<i a='ok' b=\"+\"\n>"),
                    (46, "</i>"),
                    (50, "</p>"),
                ],
            )
            # With selectors, it can still work ok.
            self.assert_source_highlights(
                self.check,
                "{ $var ->\n"
                '  [a] <img data-val="a">\n'
                " *[b] <strong>go<em>fast</em></strong>\n"
                "} and <br\t/>",
                fluent_type,
                [
                    (16, '<img data-val="a">'),
                    (41, "<strong>"),
                    (51, "<em>"),
                    (59, "</em>"),
                    (64, "</strong>"),
                    (80, "<br\t/>"),
                ],
            )
