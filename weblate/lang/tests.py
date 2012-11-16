"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

from django.test import TestCase
from weblate.lang.models import Language


class LanguagesTest(TestCase):
    TEST_LANGUAGES = (
        ('cs_CZ', 'cs', 'ltr'),
        ('de-DE', 'de', 'ltr'),
        ('de_AT', 'de_AT', 'ltr'),
        ('ar', 'ar', 'rtl'),
        ('ar_AA', 'ar', 'rtl'),
        ('ar_XX', 'ar_XX', 'rtl'),
    )
    def test_auto_create(self):
        """
        Tests that auto create correctly handles languages
        """
        for original, expected, direction in self.TEST_LANGUAGES:
            self.assertEqual(Language.objects.auto_get_or_create(original).code, expected)

    def test_rtl(self):
        '''
        Test for detecting RTL languages.
        '''
        for original, expected, direction in self.TEST_LANGUAGES:
            self.assertEqual(Language.objects.auto_get_or_create(original).direction, direction)
