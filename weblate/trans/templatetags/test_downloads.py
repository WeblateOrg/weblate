from __future__ import unicode_literals
from unittest import TestCase
from weblate.trans.templatetags.downloads import link_text, translation_download_link, translation_download_url

class Struct:
    def __init__(self, **entries):
        self.__dict__.update(entries)

def struct(dict):
    return Struct(**dict)

class RenderContextMock():
    def push_state(self, arg):
        return "test"

class Context():
    render_context = RenderContextMock()
    def get(self, what):
        if what == 'project':
            return struct({'name': 'test', 'slug': 'test'})

class ContextWithComponent(Context):
    render_context = RenderContextMock()
    def get(self, what):
        if what == 'component':
            return {'slug': 'ctest'}

        return Context.get(self, what)

class ContextWithExporter(Context):
    def get(self, what):
        if what == 'exporter':
            return {'name': 'etest'}

        return Context.get(self, what)

class ContextWithLanguage(Context):
    def get(self, what):
        if what == 'language':
            return {'code': 'de'}

        return Context.get(self, what)


class ContextWithLanguageAndExporter(ContextWithLanguage, ContextWithExporter):
    def get(self, what):
        result = ContextWithLanguage.get(self, what)
        if result == None:
            result = ContextWithExporter.get(self, what)

        return result

class DownloadTest(TestCase):
    def test_link_text_with_exporter(self):
        context = ContextWithExporter()
        self.assertEqual("etest", link_text(context))

    def test_link_text_without_exporter(self):
        context = Context()
        self.assertEqual("Original", link_text(context))

    def test_link(self):
        context = ContextWithExporter()
        expected_1 = '<a title="Download for an offline translation."'
        expected_2 = ' href="/download/test/?format=etest">etest</a>'
        self.assertEqual(expected_1 + expected_2, translation_download_link(context))

    def test_url(self):
        context = Context()
        self.assertEqual("/download/test/", translation_download_url(context))

    def test_url_with_component(self):
        context = ContextWithComponent()
        self.assertEqual("/download/test/ctest/", translation_download_url(context))


    def test_url_with_exporter(self):
        context = ContextWithExporter()
        self.assertEqual("/download/test/?format=etest", translation_download_url(context))

    def test_url_with_language(self):
        context = ContextWithLanguage()
        self.assertEqual("/download/test/?lang=de", translation_download_url(context))

    def test_url_exporter_and_lang(self):
        context = ContextWithLanguageAndExporter()
        self.assertEqual("/download/test/?format=etest&lang=de", translation_download_url(context))


