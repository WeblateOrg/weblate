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
from django.db.models.signals import post_syncdb
from weblate import appsettings
from whoosh.index import create_in, open_dir
from whoosh.writing import BufferedWriter
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


def create_source_index():
    return create_in(
        appsettings.WHOOSH_INDEX,
        schema=SOURCE_SCHEMA,
        indexname='source'
    )


def create_target_index(lang):
    return create_in(
        appsettings.WHOOSH_INDEX,
        schema=TARGET_SCHEMA,
        indexname='target-%s' % lang
    )


@receiver(post_syncdb)
def create_index(sender=None, **kwargs):
    if not os.path.exists(appsettings.WHOOSH_INDEX):
        os.mkdir(appsettings.WHOOSH_INDEX)
        create_source_index()


def flush_index():
    '''
    Flushes any possibly buffered writes to index.
    '''
    FULLTEXT_INDEX.commit()


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
    with FULLTEXT_INDEX.source_writer(buffered=False) as writer:
        source_units = source_units.values('checksum', 'source', 'context')
        for unit in source_units.iterator():
            Unit.objects.add_to_source_index(
                unit['checksum'],
                unit['source'],
                unit['context'],
                writer
            )

    # Update per language indices
    for lang in languages:
        index = FULLTEXT_INDEX.target_writer(
            lang=lang.code, buffered=False
        )
        with index as writer:

            language_units = units.filter(
                translation__language=lang
            ).exclude(
                target=''
            ).values(
                'checksum', 'target'
            )

            for unit in language_units.iterator():
                Unit.objects.add_to_target_index(
                    unit['checksum'],
                    unit['target'],
                    writer
                )


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
            try:
                self._source = open_dir(
                    appsettings.WHOOSH_INDEX,
                    indexname='source'
                )
            except whoosh.index.EmptyIndexError:
                self._source = create_source_index()
            except IOError:
                # eg. path does not exist
                self._source = create_source_index()
        return self._source

    def target(self, lang):
        '''
        Returns target index for given language.
        '''
        if not lang in self._target:
            try:
                self._target[lang] = open_dir(
                    appsettings.WHOOSH_INDEX,
                    indexname='target-%s' % lang
                )
            except whoosh.index.EmptyIndexError:
                self._target[lang] = create_target_index(lang)
        return self._target[lang]

    def source_writer(self, buffered=True):
        '''
        Returns source index writer (by default buffered).
        '''
        if not buffered:
            return self.source().writer()
        if self._source_writer is None:
            self._source_writer = BufferedWriter(self.source())
        return self._source_writer

    def target_writer(self, lang, buffered=True):
        '''
        Returns target index writer (by default buffered) for given language.
        '''
        if not buffered:
            return self.target(lang).writer()
        if not lang in self._target_writer:
            self._target_writer[lang] = BufferedWriter(self.target(lang))
        return self._target_writer[lang]

    def source_searcher(self, buffered=True):
        '''
        Returns source index searcher (on buffered writer).
        '''
        if not buffered:
            return self.source().searcher()
        return self.source_writer(buffered).searcher()

    def target_searcher(self, lang, buffered=True):
        '''
        Returns target index searcher (on buffered writer) for given language.
        '''
        if not buffered:
            return self.target(lang).searcher()
        return self.target_writer(lang, buffered).searcher()

    def commit(self):
        '''
        Commits pending changes.
        '''
        self._source_writer.commit()
        for lang in self._target_writer:
            self._target_writer[lang].commit()

FULLTEXT_INDEX = Index()
