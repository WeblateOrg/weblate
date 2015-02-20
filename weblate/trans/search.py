# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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

from whoosh.fields import SchemaClass, TEXT, ID
from whoosh.filedb.filestore import FileStorage
from whoosh import qparser
from django.db.models.signals import post_migrate
from django.db.utils import IntegrityError
from django.db import transaction
from weblate import appsettings
from whoosh.writing import AsyncWriter, BufferedWriter
from django.dispatch import receiver
from weblate.lang.models import Language
from weblate.trans.data import data_dir

STORAGE = FileStorage(data_dir('whoosh'))


class TargetSchema(SchemaClass):
    '''
    Fultext index schema for target strings.
    '''
    checksum = ID(stored=True, unique=True)
    target = TEXT()
    comment = TEXT()


class SourceSchema(SchemaClass):
    '''
    Fultext index schema for source and context strings.
    '''
    checksum = ID(stored=True, unique=True)
    source = TEXT()
    context = TEXT()
    location = TEXT()


@receiver(post_migrate)
def create_index(sender=None, **kwargs):
    '''
    Automatically creates storage directory.
    '''
    STORAGE.create()


def create_source_index():
    '''
    Creates source string index.
    '''
    return STORAGE.create_index(SourceSchema(), 'source')


def create_target_index(lang):
    '''
    Creates traget string index for given language.
    '''
    return STORAGE.create_index(TargetSchema(), 'target-%s' % lang)


def update_source_unit_index(writer, unit):
    '''
    Updates source index for given unit.
    '''
    writer.update_document(
        checksum=unicode(unit.checksum),
        source=unicode(unit.source),
        context=unicode(unit.context),
        location=unicode(unit.location),
    )


def update_target_unit_index(writer, unit):
    '''
    Updates target index for given unit.
    '''
    writer.update_document(
        checksum=unicode(unit.checksum),
        target=unicode(unit.target),
        comment=unicode(unit.comment),
    )


def get_source_index():
    '''
    Returns source index object.
    '''
    if not STORAGE.index_exists('source'):
        create_source_index()
    index = STORAGE.open_index('source')
    if 'location' not in index.schema:
        writer = index.writer()
        writer.add_field('location', TEXT)
        writer.commit()
    return index


def get_target_index(lang):
    '''
    Returns target index object.
    '''
    name = 'target-%s' % lang
    if not STORAGE.index_exists(name):
        create_target_index(lang)
    index = STORAGE.open_index(name)
    if 'comment' not in index.schema:
        writer = index.writer()
        writer.add_field('comment', TEXT)
        writer.commit()
    return index


def update_index(units, source_units=None):
    '''
    Updates fulltext index for given set of units.
    '''
    languages = Language.objects.have_translation()

    # Default to same set for both updates
    if source_units is None:
        source_units = units

    # Update source index
    index = get_source_index()
    writer = BufferedWriter(index)
    try:
        for unit in source_units.iterator():
            update_source_unit_index(writer, unit)
    finally:
        writer.close()

    # Update per language indices
    for lang in languages:
        index = get_target_index(lang.code)
        writer = BufferedWriter(index)
        try:
            language_units = units.filter(
                translation__language=lang
            ).exclude(
                target=''
            )

            for unit in language_units.iterator():
                update_target_unit_index(writer, unit)
        finally:
            writer.close()


def update_index_unit(unit, source=True):
    '''
    Adds single unit to index.
    '''
    # Should this happen in background?
    if appsettings.OFFLOAD_INDEXING:
        from weblate.trans.models.search import IndexUpdate
        try:
            with transaction.atomic():
                IndexUpdate.objects.create(
                    unit=unit,
                    source=source,
                )
        # pylint: disable=E0712
        except IntegrityError:
            try:
                update = IndexUpdate.objects.get(unit=unit)
                if not update.source and source:
                    update.source = True
                    update.save()
            except IndexUpdate.DoesNotExist:
                # It did exist, but was deleted meanwhile
                return
        return

    # Update source
    if source:
        index = get_source_index()
        with AsyncWriter(index) as writer:
            update_source_unit_index(writer, unit)

    # Update target
    if unit.target != '':
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


def fulltext_search(query, lang, params):
    '''
    Performs fulltext search in given areas, returns set of checksums.
    '''
    checksums = set()

    search = {
        'source': False,
        'context': False,
        'target': False,
        'comment': False,
        'location': False,
    }
    search.update(params)

    if search['source'] or search['context'] or search['location']:
        index = get_source_index()
        with index.searcher() as searcher:
            for param in ('source', 'context', 'location'):
                if search[param]:
                    checksums.update(
                        base_search(searcher, param, SourceSchema(), query)
                    )

    if search['target'] or search['comment']:
        index = get_target_index(lang)
        with index.searcher() as searcher:
            for param in ('target', 'comment'):
                if search[param]:
                    checksums.update(
                        base_search(searcher, param, TargetSchema(), query)
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
