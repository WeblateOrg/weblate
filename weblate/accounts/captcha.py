#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
"""Simple mathematical captcha."""


import ast
import operator
import time
from random import SystemRandom

from weblate.utils.templatetags.icons import icon

TIMEDELTA = 600

# Supported operators
OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul}


class MathCaptcha:
    """Simple match captcha object."""

    operators = ("+", "-", "*")
    operators_display = {}
    interval = (1, 10)

    def __init__(self, question=None, timestamp=None):
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
        return parts[0] + " " + self.operators_display[parts[1]] + " " + parts[2]


def eval_expr(expr):
    """Evaluate arithmetic expression used in Captcha.

    >>> eval_expr('2+6')
    8
    >>> eval_expr('2*6')
    12
    """
    return eval_node(ast.parse(expr).body[0].value)


def eval_node(node):
    """Evaluate single AST node."""
    if isinstance(node, ast.Num):
        # number
        return node.n
    if isinstance(node, ast.operator):
        # operator
        return OPERATORS[type(node)]
    if isinstance(node, ast.BinOp):
        # binary operation
        return eval_node(node.op)(eval_node(node.left), eval_node(node.right))
    raise ValueError(node)
