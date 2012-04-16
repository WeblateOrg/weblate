'''
Whoosh based full text search.
'''

import whoosh
import os
from whoosh.fields import Schema, TEXT, ID
from django.db.models.signals import post_syncdb
from django.conf import settings
from whoosh.index import create_in, open_dir
from whoosh.writing import BufferedWriter

TARGET_SCHEMA = Schema(
    checksum = ID(stored = True, unique = True),
    target = TEXT
)

SOURCE_SCHEMA = Schema(
    checksum = ID(stored = True, unique = True),
    source = TEXT,
    context = TEXT
)

def create_source_index():
    return create_in(
        settings.WHOOSH_INDEX,
        schema = SOURCE_SCHEMA,
        indexname = 'source'
    )

def create_target_index(lang):
    return create_in(
        settings.WHOOSH_INDEX,
        schema = TARGET_SCHEMA,
        indexname = 'target-%s' % lang
    )

def create_index(sender=None, **kwargs):
    if not os.path.exists(settings.WHOOSH_INDEX):
        os.mkdir(settings.WHOOSH_INDEX)
        create_source_index()

post_syncdb.connect(create_index)

class Index(object):
    '''
    Class to manage index readers and writers.
    '''

    _source = None
    _target = {}
    _source_writer = None
    _target_writer = {}

    def source(self):
        '''
        Returns source index.
        '''
        if self._source is None:
            self._source = open_dir(
                settings.WHOOSH_INDEX,
                indexname = 'source'
            )
        return self._source

    def target(self, lang):
        '''
        Returns target index for given language.
        '''
        if not lang in self._target:
            try:
                self._target[lang] = open_dir(
                    settings.WHOOSH_INDEX,
                    indexname = 'target-%s' % lang
                )
            except whoosh.index.EmptyIndexError:
                self._target[lang] = create_target_index(lang)
        return self._target[lang]

    def source_writer(self, buffered = True):
        '''
        Returns source index writer (by default buffered).
        '''
        if not buffered:
            return self.source().writer()
        if self._source_writer is None:
            self._source_writer = BufferedWriter(self.source())
        return self._source_writer

    def target_writer(self, lang, buffered = True):
        '''
        Returns target index writer (by default buffered) for given language.
        '''
        if not buffered:
            return self.target(lang).writer()
        if not lang in self._target_writer:
            self._target_writer[lang] = BufferedWriter(self.target(lang))
        return self._target_writer[lang]

    def source_searcher(self):
        '''
        Returns source index searcher (on buffered writer).
        '''
        return self.source_writer().searcher()

    def target_searcher(self, lang):
        '''
        Returns target index searcher (on buffered writer) for given language.
        '''
        return self.target_writer(lang).searcher()

FULLTEXT_INDEX = Index()
