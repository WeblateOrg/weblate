"""
Tests for consistency checks.
"""

from django.test import TestCase
from weblate.trans.checks import SameCheck


class Language(object):
    '''
    Mock language object.
    '''
    def __init__(self, code):
        self.code = code


class CheckTest(TestCase):
    def test_same(self):
        check = SameCheck()
        self.assertFalse(check.check_single(
            'source',
            'translation',
            '',
            Language('cs'),
            None
        ))
