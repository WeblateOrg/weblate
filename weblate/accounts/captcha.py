# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Simple mathematical captcha."""

import ast
import base64
import json
import operator
import time
import urllib.parse
from random import SystemRandom

from altcha import Challenge, Solution, solve_challenge
from django.utils.html import format_html

from weblate.utils.templatetags.icons import icon

TIMEDELTA = 600

# Supported operators
OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul}


class MathCaptcha:
    """Simple match captcha object."""

    operators = ("+", "-", "*")
    operators_display = {}
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
        if not self.operators_display:
            self.operators_display = {
                "+": icon("plus.svg"),
                "-": icon("minus.svg"),
                "*": icon("close.svg"),
            }

    def generate_question(self):
        """Generate random question."""
        generator = SystemRandom()
        operation = generator.choice(self.operators)
        first = generator.randint(self.interval[0], self.interval[1])
        second = generator.randint(self.interval[0], self.interval[1])

        # We don't want negative answers
        if operation == "-":
            first += self.interval[1]

        return str(first) + " " + operation + " " + str(second)

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
        return format_html(
            "{} {} {}", parts[0], self.operators_display[parts[1]], parts[2]
        )


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


def solve_altcha(challenge: Challenge, number: int | None = None) -> str:
    solution: Solution = solve_challenge(
        challenge=challenge.challenge,
        salt=challenge.salt,
        algorithm=challenge.algorithm,
        max_number=challenge.maxnumber,
        start=0,
    )
    # Make sure the challenge expiry is in past
    split_salt = challenge.salt.split("?")
    params = urllib.parse.parse_qs(split_salt[1])
    expires = int(params["expires"][0])
    while time.time() == expires:
        time.sleep(0.1)
    return base64.b64encode(
        json.dumps(
            {
                "algorithm": challenge.algorithm,
                "challenge": challenge.challenge,
                "number": solution.number if number is None else number,
                "salt": challenge.salt,
                "signature": challenge.signature,
            }
        ).encode("utf-8")
    ).decode("utf-8")
