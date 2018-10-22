from __future__ import unicode_literals
from unittest import TestCase
from weblate.trans.templatetags.download import link_text


class Context():
    def get(what):
        return "test"

class DownloadTest(TestCase):
    def test_defaults(self):
        context = Context()
        self.assertEqual(link_text(context), link_text(context))
