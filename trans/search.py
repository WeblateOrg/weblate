# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

'''
Whoosh based full text search.
'''

import whoosh
import os
from whoosh.fields import Schema, TEXT, ID
from whoosh.filedb.filestore import FileStorage
from whoosh import qparser
from django.db.models.signals import post_syncdb
from weblate import appsettings
from whoosh.index import create_in, open_dir
from whoosh.writing import AsyncWriter, BufferedWriter
from django.dispatch import receiver
from lang.models import Language

TARGET_SCHEMA = Schema(
    checksum=ID(stored=True, unique=True),
    target=TEXT
)

SOURCE_SCHEMA = Schema(
    checksum=ID(stored=True, unique=True),
    source=TEXT,
    context=TEXT
)

STORAGE = FileStorage(appsettings.WHOOSH_INDEX)


@receiver(post_syncdb)
def create_index(sender=None, **kwargs):
    '''
    Automatically creates storage directory.
    '''
    STORAGE.create()


def create_source_index():
    '''
    Creates source string index.
    '''
    return STORAGE.create_index(SOURCE_SCHEMA, 'source')


def create_target_index(lang):
    '''
    Creates traget string index for given language.
    '''
    return STORAGE.create_index(TARGET_SCHEMA, 'target-%s' % lang)


def update_source_unit_index(writer, unit):
    '''
    Updates source index for given unit.
    '''
    writer.update_document(
        checksum=unicode(unit.checksum),
        source=unicode(unit.source),
        context=unicode(unit.context),
    )


def update_target_unit_index(writer, unit):
    '''
    Updates target index for given unit.
    '''
    writer.update_document(
        checksum=unicode(unit.checksum),
        target=unicode(unit.target)
    )


def get_source_index():
    '''
    Returns source index object.
    '''
    if not STORAGE.index_exists('source'):
        create_source_index()
    return STORAGE.open_index('source')


def get_target_index(lang):
    '''
    Returns target index object.
    '''
    name = 'target-%s' % lang
    if not STORAGE.index_exists(name):
        create_target_index(lang)
    return STORAGE.open_index(name)


def update_index(units, source_units=None):
    '''
    Updates fulltext index for given set of units.
    '''
    from trans.models import Unit
    languages = Language.objects.all()

    # Default to same set for both updates
    if source_units is None:
        source_units = units

    # Update source index
    index = get_source_index()
    with BufferedWriter(index) as writer:
        for unit in source_units.iterator():
            update_source_unit_index(writer, unit)

    # Update per language indices
    for lang in languages:
        index = get_target_index(lang.code)
        with BufferedWriter(index) as writer:

            language_units = units.filter(
                translation__language=lang
            ).exclude(
                target=''
            )

            for unit in language_units.iterator():
                update_target_unit_index(writer, unit)


def update_index_unit(unit, source=True):
    '''
    Adds single unit to index.
    '''
    # Should this happen in background?
    if appsettings.OFFLOAD_INDEXING:
        from trans.models.unitdata import IndexUpdate
        IndexUpdate.objects.create(unit=unit, source=source)
        return

    # Update source
    if source:
        index = get_source_index()
        with AsyncWriter(index) as writer:
            update_source_unit_index(writer, unit)

    # Update target
    if unit.translated:
        index = get_target_index(unit.translation.language.code)
        with AsyncWriter(index) as writer:
            update_target_unit_index(writer, unit)


def base_search(searcher, field, schema, query):
    '''
    Wrapper for fulltext search.
    '''
    parser = qparser.QueryParser(field, schema)
    parsed = parser.parse(query)
    return [result['checksum'] for result in searcher.search(parsed)]


def fulltext_search(query, lang, source=True, context=True, target=True):
    '''
    Performs fulltext search in given areas, returns set of checksums.
    '''
    checksums = set()

    if source or context:
        index = get_source_index()
        with index.searcher() as searcher:
            if source:
                checksums.update(
                    base_search(searcher, 'source', SOURCE_SCHEMA, query)
                )
            if context:
                checksums.update(
                    base_search(searcher, 'context', SOURCE_SCHEMA, query)
                )

    if target:
        index = get_target_index(lang)
        with index.searcher() as searcher:
            checksums.update(
                base_search(searcher, 'target', TARGET_SCHEMA, query)
            )

    return checksums


def more_like(checksum, source, top=5):
    '''
    Finds similar units.
    '''
    index = get_source_index()
    with index.searcher() as searcher:
        docnum = searcher.document_number(checksum=checksum)
        if docnum is None:
            return set()

        results = searcher.more_like(docnum, 'source', source, top)

        return set([result['checksum'] for result in results])


def flush_caches():
    '''
    Flushes internal caches.
    '''
    FULLTEXT_INDEX.flush_caches()


class Index(object):
    '''
    Class to manage index readers and writers.
    '''

    _source = None
    _target = {}

    def __init__(self):
        '''
        Creates searcher object.
        '''
        self.storage = FileStorage(appsettings.WHOOSH_INDEX)

    def source(self):
        '''
        Returns source index.
        '''
        if self._source is None:
            try:
                self._source = self.storage.open_index(
                    indexname='source',
                    schema=SOURCE_SCHEMA,
                )
            except (whoosh.index.EmptyIndexError, IOError):
                # eg. path or index does not exist
                self._source = create_source_index()
        return self._source

    def target(self, lang):
        '''
        Returns target index for given language.
        '''
        if not lang in self._target:
            try:
                self._target[lang] = self.storage.open_index(
                    indexname='target-%s' % lang,
                    schema=TARGET_SCHEMA,
                )
            except (whoosh.index.EmptyIndexError, IOError):
                self._target[lang] = create_target_index(lang)
        return self._target[lang]

    def source_writer(self, async=True):
        '''
        Returns source index writer (by default buffered).
        '''
        if async:
            return AsyncWriter(self.source())
        return self.source().writer()

    def target_writer(self, lang, async=True):
        '''
        Returns target index writer (by default buffered) for given language.
        '''
        if async:
            return AsyncWriter(self.target(lang))
        return self.target(lang).writer()

    def source_searcher(self):
        '''
        Returns source index searcher (on buffered writer).
        '''
        return self.source().searcher()

    def target_searcher(self, lang):
        '''
        Returns target index searcher (on buffered writer) for given language.
        '''
        return self.target(lang).searcher()

    def flush_caches(self):
        '''
        Flushes internal caches.
        '''
        self._source = None
        self._target = {}

FULLTEXT_INDEX = Index()
