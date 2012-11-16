"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

from django.test import TestCase
from weblate.lang.models import Language


class LanguagesTest(TestCase):
    AUTO_CREATE_LANGUAGES = (
        ('cs_CZ', 'cs'),
        ('de-DE', 'de'),
        ('de_AT', 'de_AT'),
    )
    def test_auto_create(self):
        """
        Tests that auto create correctly handles languages
        """
        for original, expected in self.AUTO_CREATE_LANGUAGES:
            self.assertEqual(Language.objects.auto_get_or_create(original).code, expected)
