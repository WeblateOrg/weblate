"""
Tests for consistency checks.
"""

from django.test import TestCase
from weblate.trans.checks import SameCheck, BeginNewlineCheck


class Language(object):
    '''
    Mock language object.
    '''
    def __init__(self, code):
        self.code = code


class SameCheckTest(TestCase):
    def setUp(self):
        self.check = SameCheck()

    def test_not_same(self):
        self.assertFalse(self.check.check_single(
            'source',
            'translation',
            '',
            Language('cs'),
            None
        ))

    def test_same(self):
        self.assertTrue(self.check.check_single(
            'source',
            'source',
            '',
            Language('cs'),
            None
        ))

    def test_same_english(self):
        self.assertFalse(self.check.check_single(
            'source',
            'source',
            '',
            Language('en'),
            None
        ))

    def test_same_format(self):
        self.assertFalse(self.check.check_single(
            '%(source)s',
            '%(source)s',
            'python-format',
            Language('cs'),
            None
        ))


class BeginNewlineCheckTest(TestCase):
    def setUp(self):
        self.check = BeginNewlineCheck()

    def test_newline(self):
        self.assertFalse(self.check.check_single(
            '\nstring',
            '\nstring',
            '',
            Language('cs'),
            None
        ))

    def test_no_newline(self):
        self.assertTrue(self.check.check_single(
            '\nstring',
            ' \nstring',
            '',
            Language('cs'),
            None
        ))
