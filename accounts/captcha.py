# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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


from django.conf import settings

import hashlib
from random import randint, choice


class MathCaptcha(object):
    '''
    Simple match captcha object.
    '''
    operators = ('+', '-', '*')
    interval = (0, 10)

    def __init__(self, question=None):
        if question is None:
            self.question = self.generate_question()
        else:
            self.question = question

        pass

    def generate_question(self):
        '''
        Generates random question.
        '''
        x = randint(self.interval[0], self.interval[1])
        y = randint(self.interval[0], self.interval[1])

        # We don't want negative answers
        if y > x:
            x, y = y, x
        return '%d %s %d' % (
            x,
            choice(self.operators),
            y
        )

    @staticmethod
    def from_hash(hashed):
        '''
        Creates object from hash.
        '''
        question = unhash_question(hashed)
        return MathCaptcha(question)

    @property
    def hashed(self):
        '''
        Returns hashed question.
        '''
        return hash_question(self.question)

    def validate(self, answer):
        '''
        Validates answer.
        '''
        result = eval(self.question)
        return result == answer


def checksum_question(question):
    '''
    Returns checksum for a question.
    '''
    sha = hashlib.sha1(settings.SECRET_KEY + question)
    return sha.hexdigest()


def hash_question(question):
    '''
    Hashes question so that it can be later verified.
    '''
    hexsha = checksum_question(question)
    return '%s%s' % (
        hexsha,
        question.encode('hex')
    )


def unhash_question(question):
    '''
    Unhashes question, verifying it's content.
    '''
    if len(question) < 40:
        raise ValueError('Invalid data')
    hexsha = question[:40]
    question = question[40:].decode('hex')
    if hexsha != checksum_question(question):
        raise ValueError('Tampered question!')
    return question
