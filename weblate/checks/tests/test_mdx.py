# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.checks.mdx import SafeMDXCheck
from weblate.checks.tests.test_checks import CheckTestCase


class SafeMDXCheckTest(CheckTestCase):
    check = SafeMDXCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = (
            "Hello, {props.name.toUpperCase()}",
            "Ahoj, {props.name.toUpperCase()}",
            "safe-mdx",
        )

        self.test_failure_1 = (
            "Hello, {props.name.toUpperCase()}",
            "Ahoj, {props.unauthorized.access()}",
            "safe-mdx",
        )
        self.test_failure_2 = ("Test {Math.PI * 100}", "Test {Math.PI*100}", "safe-mdx")
        self.test_failure_3 = ("Hello, {props.name.toUpperCase()}", "Ahoj", "safe-mdx")
        self.test_failure_4 = (
            '<a href="/profile">{userName}</a>',
            "<a href={userName}>View profile</a>",
            "safe-mdx",
        )
        self.test_failure_5 = (
            "<Card title={title}>{body}</Card>",
            "<Card title={body}>{title}</Card>",
            "safe-mdx",
        )
        self.test_ignore_check = (
            "Hello, {test}",
            "Ahoj, {ignore}",
            "safe-mdx,ignore-safe-mdx",
        )

    def test_complex_expressions(self) -> None:
        self.check_jsx_expression_matches(
            "Expression one {[1, 2, 3].map(({ id }) => (<p key={id}>{id}</p>))} and two {[1, 2, 3].map(({ id }) => (<p key={id}>{id}</p>))}",
            [
                "{[1, 2, 3].map(({ id }) => (<p key={id}>{id}</p>))}",
                "{[1, 2, 3].map(({ id }) => (<p key={id}>{id}</p>))}",
            ],
        )
        self.check_jsx_expression_matches(
            "Test {[1, 2, 3].map(({ id }) => (<p key={id}>{id}</p>))}",
            ["{[1, 2, 3].map(({ id }) => (<p key={id}>{id}</p>))}"],
        )
        self.check_jsx_expression_matches(
            "Test { `}}` + 'count' }",
            ["{ `}}` + 'count' }"],
        )
        self.check_jsx_expression_matches(
            "Test { `{{` + 'count' + `}}` }",
            ["{ `{{` + 'count' + `}}` }"],
        )
        # Braces inside a string literal must not break expression boundaries.
        self.check_jsx_expression_matches(
            'Show {label("}")} here',
            ['{label("}")}'],
        )
        # Braces inside a block comment are ignored.
        self.check_jsx_expression_matches(
            "Value {x /* } */ + y}",
            ["{x /* } */ + y}"],
        )
        # Braces inside a regex literal (including a character class) are ignored.
        self.check_jsx_expression_matches(
            'Clean {s.replace(/[{}]/g, "")}',
            ['{s.replace(/[{}]/g, "")}'],
        )
        # Template literal interpolation is part of the expression.
        self.check_jsx_expression_matches(
            "Total {`sum: ${a + b}`}",
            ["{`sum: ${a + b}`}"],
        )
        # Escaped braces are literal text, not expressions; only {real} counts.
        self.check_jsx_expression_matches(
            "Price \\{literal\\} and {real}",
            ["{real}"],
        )
        self.check_jsx_expression_matches(
            "Price {literal} and {real}",
            ["{literal}", "{real}"],
        )
        # Braces inside a Markdown inline code span are literal text.
        self.check_jsx_expression_matches(
            "Use `{notExpr}` but {expr}",
            ["{expr}"],
        )
        self.check_jsx_expression_matches(
            "Test \\{{count1} `{inside_thiings}` and then {count2}",
            ["{count1}", "{count2}"],
        )
        # Nested destructuring with a default object literal.
        self.check_jsx_expression_matches(
            "{({ a = { x: 1 } }) => a}",
            ["{({ a = { x: 1 } }) => a}"],
        )
        # JSX element with nested expression attributes.
        self.check_jsx_expression_matches(
            "{<Icon name={`star`} count={3} />}",
            ["{<Icon name={`star`} count={3} />}"],
        )
        # Regex following an arrow symbol
        self.check_jsx_expression_matches(
            "{items.filter(x => /}/.test(x)).length}",
            ["{items.filter(x => /}/.test(x)).length}"],
        )
        self.check_jsx_expression_matches(
            "{arr.map(x => /a}b/)}",
            ["{arr.map(x => /a}b/)}"],
        )
        # A regex following a comparison operator >
        self.check_jsx_expression_matches(
            "{a > /x}y/.source.length}",
            ["{a > /x}y/.source.length}"],
        )
        # ``<`` stays excluded so the ``/`` in a JSX closing tag is not misread
        # as the start of a regex literal that would swallow the closing brace.
        self.check_jsx_expression_matches(
            "{cond ? <p>{a}</p> : null}",
            ["{cond ? <p>{a}</p> : null}"],
        )

    def check_jsx_expression_matches(self, text: str, expected: list[str]) -> None:
        self.assertEqual(
            list(self.check.get_jsx_expression_matches(text)),
            expected,
        )

    def test_expression_signatures_include_context(self) -> None:
        self.assertEqual(
            list(
                self.check.get_jsx_expression_signatures(
                    '<a href="/profile">{userName}</a>'
                )
            ),
            [("text", "", ("a",), "{userName}")],
        )
        self.assertEqual(
            list(
                self.check.get_jsx_expression_signatures(
                    "<a href={userName}>View profile</a>"
                )
            ),
            [("attribute", "href", ("a",), "{userName}")],
        )
