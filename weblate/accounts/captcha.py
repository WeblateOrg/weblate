# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Simple mathematical captcha."""

from __future__ import annotations

import ast
import operator
import time
from functools import cache
from random import SystemRandom
from typing import TYPE_CHECKING, Literal

from altcha import Payload, solve_challenge
from django.utils.html import format_html

from weblate.utils.templatetags.icons import icon

if TYPE_CHECKING:
    from altcha import Challenge, Solution

TIMEDELTA = 600

# Supported operators
OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul}


class InvalidOperatorError(ValueError):
    """Invalid operator for display."""


@cache
def operator_display(name: Literal["+", "-", "*"]) -> str:
    match name:
        case "+":
            return icon("plus.svg")
        case "-":
            return icon("minus.svg")
        case "*":
            return icon("close.svg")
    raise InvalidOperatorError


class MathCaptcha:
    """Simple match captcha object."""

    operators = ("+", "-", "*")
    interval = (1, 10)

    def __init__(self, question=None, timestamp=None) -> None:
        if question is None:
            self.question = self.generate_question()
        else:
            self.question = question
        if timestamp is None:
            self.timestamp = time.time()
        else:
            self.timestamp = timestamp

    def generate_question(self):
        """Generate random question."""
        generator = SystemRandom()
        operation = generator.choice(self.operators)
        first = generator.randint(self.interval[0], self.interval[1])
        second = generator.randint(self.interval[0], self.interval[1])

        # We don't want negative answers
        if operation == "-":
            first += self.interval[1]

        return f"{first!s} {operation} {second!s}"

    @staticmethod
    def unserialize(value):
        """Create object from serialized."""
        return MathCaptcha(*value)

    def serialize(self):
        """Serialize captcha settings."""
        return (self.question, self.timestamp)

    def validate(self, answer):
        """Validate answer."""
        return self.result == answer and self.timestamp + TIMEDELTA > time.time()

    @property
    def result(self):
        """Return result."""
        return eval_expr(self.question)

    @property
    def display(self):
        """Get unicode for display."""
        parts = self.question.split()
        return format_html("{} {} {}", parts[0], operator_display(parts[1]), parts[2])


def eval_expr(expr):
    """
    Evaluate arithmetic expression used in Captcha.

    >>> eval_expr("2+6")
    8
    >>> eval_expr("2*6")
    12
    """
    return eval_node(ast.parse(expr).body[0].value)


def eval_node(node):
    """Evaluate single AST node."""
    if isinstance(node, ast.Constant):
        # number
        return node.value
    if isinstance(node, ast.operator):
        # operator
        return OPERATORS[type(node)]
    if isinstance(node, ast.BinOp):
        # binary operation
        return eval_node(node.op)(eval_node(node.left), eval_node(node.right))
    raise ValueError(node)


def solve_altcha(challenge: Challenge, *, invalid: bool = False) -> str:
    solution: Solution | None = solve_challenge(challenge)
    if solution is None:
        msg = "Unable to solve ALTCHA challenge"
        raise ValueError(msg)
    # Make sure the challenge expiry is in past
    expires = challenge.parameters.expires_at
    while time.time() == expires:
        time.sleep(0.1)
    if invalid:
        # Tampering with counter would raise struct.error (packed as uint32),
        # so corrupt the derived key instead to force a verification failure.
        solution.derived_key = "0" * len(solution.derived_key)
    return Payload(
        challenge=challenge,
        solution=solution,
    ).to_base64()
