from __future__ import unicode_literals
from unittest import TestCase
from weblate.trans.templatetags.downloads import link_text, translation_download_link, translation_download_url

class RenderContextMock():
    def push_state(self, arg):
        return "test";

class Context():
    render_context = RenderContextMock()
    def get(self, what):
        if what == 'project':
            return {'name': 'test', 'slug': 'test'}
        elif what == 'exporter':
            return {'name': 'test'}

class ContextWithComponent(Context):
    render_context = RenderContextMock()
    def get(self, what):
        if what == 'component':
            return { 'slug': 'ctest' }

        return Context.get(self, what)

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
        self.assertEqual('<a title="Download for an offline translation." href="/download/test/">test</a>', translation_download_link(context))

    def test_url(self):
        context = Context();
        self.assertEqual("/download/test/", translation_download_url(context))

    def test_url_with_component(self):
        context = ContextWithComponent();
        self.assertEqual("/download/test/ctest/", translation_download_url(context))



