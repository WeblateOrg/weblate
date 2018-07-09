# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

import ast
from base64 import b64encode, b64decode
import hashlib
import operator
from random import SystemRandom
import time
from django.conf import settings

TIMEDELTA = 600

# Supported operators
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
}


class MathCaptcha(object):
    """Simple match captcha object."""
    operators = ('+', '-', '*')
    operators_display = {
        '+': '<i class="fa fa-plus"></i>',
        '-': '<i class="fa fa-minus"></i>',
        '*': '<i class="fa fa-times"></i>',
    }
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

    def generate_question(self):
        """Generate random question."""
        generator = SystemRandom()
        operation = generator.choice(self.operators)
        first = generator.randint(self.interval[0], self.interval[1])
        second = generator.randint(self.interval[0], self.interval[1])

        # We don't want negative answers
        if operation == '-':
            first += self.interval[1]

        return ' '.join((
            str(first),
            operation,
            str(second)
        ))

    @staticmethod
    def from_hash(hashed):
        """Create object from hash."""
        question, timestamp = unhash_question(hashed)
        return MathCaptcha(question, timestamp)

    @property
    def hashed(self):
        """Return hashed question."""
        return hash_question(self.question, self.timestamp)

    def validate(self, answer):
        """Validate answer."""
        return (
            self.result == answer and
            self.timestamp + TIMEDELTA > time.time()
        )

    @property
    def result(self):
        """Return result."""
        return eval_expr(self.question)

    @property
    def display(self):
        """Get unicode for display."""
        parts = self.question.split()
        return ' '.join((
            parts[0],
            self.operators_display[parts[1]],
            parts[2],
        ))


def format_timestamp(timestamp):
    """Format timestamp in a form usable in captcha."""
    return '{0:>010x}'.format(int(timestamp))


def checksum_question(question, timestamp):
    """Return checksum for a question."""
    challenge = ''.join((settings.SECRET_KEY, question, timestamp))
    sha = hashlib.sha1(challenge.encode('utf-8'))
    return sha.hexdigest()


def hash_question(question, timestamp):
    """Hashe question so that it can be later verified."""
    timestamp = format_timestamp(timestamp)
    hexsha = checksum_question(question, timestamp)
    return ''.join((
        hexsha,
        timestamp,
        b64encode(question.encode('utf-8')).decode('ascii')
    ))


def unhash_question(question):
    """Unhashe question, verifying its content."""
    if len(question) < 40:
        raise ValueError('Invalid data')
    hexsha = question[:40]
    timestamp = question[40:50]
    try:
        question = b64decode(question[50:]).decode('utf-8')
    except (TypeError, UnicodeError):
        raise ValueError('Invalid encoding')
    if hexsha != checksum_question(question, timestamp):
        raise ValueError('Tampered question!')
    return question, int(timestamp, 16)


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
    elif isinstance(node, ast.operator):
        # operator
        return OPERATORS[type(node)]
    elif isinstance(node, ast.BinOp):
        # binary operation
        return eval_node(node.op)(
            eval_node(node.left),
            eval_node(node.right)
        )
    else:
        raise ValueError(node)
