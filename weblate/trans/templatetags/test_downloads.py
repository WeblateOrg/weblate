from __future__ import unicode_literals
from unittest import TestCase
from weblate.trans.templatetags.downloads import link_text, translation_download_link, translation_download_url

class RenderContextMock():
    def push_state(self, arg):
        return "test";

class Context():
    render_context = RenderContextMock()
    def get(self, what):
        return {'name': 'test'}

class ContextNoExport():
    def get(self, what):
        return None

class DownloadTest(TestCase):
    def test_link_text_with_exporter(self):
        context = Context()
        self.assertEqual("test", link_text(context))

    def test_link_text_without_exporter(self):
        context = ContextNoExport()
        self.assertEqual("Original", link_text(context))

    def test_link(self):
        context = Context();
        self.assertEqual('<a title="Download for an offline translation." href="testUrl">test</a>', translation_download_link(context))

    def test_url(self):
        context = Context();
        self.assertEqual("testUrl", translation_download_url(context))


