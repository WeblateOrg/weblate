from __future__ import unicode_literals
from unittest import TestCase
from weblate.trans.templatetags.downloads import link_text

class Context():
    def get(what):
        return {'name': 'test'}

class ContextNoExport():
    def get(what):
        return Null

class DownloadTest(TestCase):
    def test_with_exporter(self):
        context = Context()
        self.assertEqual("test", link_text(context))

    def test_without_exporter(self):
        context = ContextNoExport()
        self.assertEqual("Original", link_text(context))

    #def test_without_context(self):
    #    #pending
    #    # test for: Exception is thrown

    #def test_shows_format_name_if_its_only_one(self):
    #    #pending

    #def test_omits_format_name_information_completely_if_there_are_multiple_formats(self):
    #    #pending

