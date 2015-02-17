# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Simple mathematical captcha.
"""


from django.conf import settings

import hashlib
import binascii
import time
from random import randint, choice
import ast
import operator

TIMEDELTA = 600

# Supported operators
OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
}


class MathCaptcha(object):
    '''
    Simple match captcha object.
    '''
    operators = ('+', '-', '*')
    operators_display = {
        '+': u'＋',
        '-': u'－',
        '*': u'×',
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
        '''
        Generates random question.
        '''
        operation = choice(self.operators)
        first = randint(self.interval[0], self.interval[1])
        second = randint(self.interval[0], self.interval[1])

        # We don't want negative answers
        if operation == '-':
            first += self.interval[1]

        return '{0} {1} {2}'.format(
            first,
            operation,
            second
        )

    @staticmethod
    def from_hash(hashed):
        '''
        Creates object from hash.
        '''
        question, timestamp = unhash_question(hashed)
        return MathCaptcha(question, timestamp)

    @property
    def hashed(self):
        '''
        Returns hashed question.
        '''
        return hash_question(self.question, self.timestamp)

    def validate(self, answer):
        '''
        Validates answer.
        '''
        return (
            self.result == answer and
            self.timestamp + TIMEDELTA > time.time()
        )

    @property
    def result(self):
        '''
        Returns result.
        '''
        return eval_expr(self.question)

    @property
    def display(self):
        '''
        Gets unicode for display.
        '''
        parts = self.question.split()
        return u'{0} {1} {2}'.format(
            parts[0],
            self.operators_display[parts[1]],
            parts[2],
        )


def format_timestamp(timestamp):
    '''
    Formats timestamp in a form usable in captcha.
    '''
    return '{0:>010x}'.format(int(timestamp))


def checksum_question(question, timestamp):
    '''
    Returns checksum for a question.
    '''
    sha = hashlib.sha1(settings.SECRET_KEY + question + timestamp)
    return sha.hexdigest()


def hash_question(question, timestamp):
    '''
    Hashes question so that it can be later verified.
    '''
    timestamp = format_timestamp(timestamp)
    hexsha = checksum_question(question, timestamp)
    return '{0}{1}{2}'.format(
        hexsha,
        timestamp,
        question.encode('base64')
    )


def unhash_question(question):
    '''
    Unhashes question, verifying it's content.
    '''
    if len(question) < 40:
        raise ValueError('Invalid data')
    hexsha = question[:40]
    timestamp = question[40:50]
    try:
        question = question[50:].decode('base64')
    except binascii.Error:
        raise ValueError('Invalid encoding')
    if hexsha != checksum_question(question, timestamp):
        raise ValueError('Tampered question!')
    return question, int(timestamp, 16)


def eval_expr(expr):
    """
    Evaluates arithmetic expression used in Captcha.

    >>> eval_expr('2+6')
    8
    >>> eval_expr('2*6')
    12
    """
    return eval_node(ast.parse(expr).body[0].value)


def eval_node(node):
    """
    Evaluates single AST node.
    """
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
