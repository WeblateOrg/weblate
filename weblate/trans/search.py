# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
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

import functools
import shutil
from whoosh.fields import SchemaClass, TEXT, NUMERIC
from whoosh.filedb.filestore import FileStorage
from whoosh.writing import AsyncWriter, BufferedWriter
from whoosh import qparser
from django.dispatch import receiver
from django.db.models.signals import post_migrate
from django.db.utils import IntegrityError
from django.utils.encoding import force_text
from django.db import transaction
from weblate import appsettings
from weblate.lang.models import Language
from weblate.trans.data import data_dir

STORAGE = FileStorage(data_dir('whoosh'))


class TargetSchema(SchemaClass):
    '''
    Fultext index schema for target strings.
    '''
    pk = NUMERIC(stored=True, unique=True)
    target = TEXT()
    comment = TEXT()


class SourceSchema(SchemaClass):
    '''
    Fultext index schema for source and context strings.
    '''
    pk = NUMERIC(stored=True, unique=True)
    source = TEXT()
    context = TEXT()
    location = TEXT()


def clean_indexes():
    """
    Cleans all indexes.
    """
    shutil.rmtree(data_dir('whoosh'))
    create_index()


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
    create_index()
    return STORAGE.create_index(SourceSchema(), 'source')


def create_target_index(lang):
    '''
    Creates traget string index for given language.
    '''
    create_index()
    return STORAGE.create_index(TargetSchema(), 'target-%s' % lang)


def update_source_unit_index(writer, unit):
    '''
    Updates source index for given unit.
    '''
    writer.update_document(
        pk=unit.pk,
        source=force_text(unit.source),
        context=force_text(unit.context),
        location=force_text(unit.location),
    )


def update_target_unit_index(writer, unit):
    '''
    Updates target index for given unit.
    '''
    writer.update_document(
        pk=unit.pk,
        target=force_text(unit.target),
        comment=force_text(unit.comment),
    )


def get_source_index():
    '''
    Returns source index object.
    '''
    try:
        exists = STORAGE.index_exists('source')
    except OSError:
        create_index()
        exists = False
    if not exists:
        create_source_index()
    index = STORAGE.open_index('source')
    if 'location' not in index.schema:
        index.add_field('location', TEXT())
    if 'pk' not in index.schema:
        index.add_field('pk', NUMERIC(stored=True, unique=True))
    if 'checksum' in index.schema:
        index.remove_field('checksum')
    return index


def get_target_index(lang):
    '''
    Returns target index object.
    '''
    name = 'target-%s' % lang
    try:
        exists = STORAGE.index_exists(name)
    except OSError:
        create_index()
        exists = False
    if not exists:
        create_target_index(lang)
    index = STORAGE.open_index(name)
    if 'comment' not in index.schema:
        index.add_field('comment', TEXT())
    if 'pk' not in index.schema:
        index.add_field('pk', NUMERIC(stored=True, unique=True))
    if 'checksum' in index.schema:
        index.remove_field('checksum')
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
    if source_units.exists():
        index = get_source_index()
        writer = BufferedWriter(index)
        try:
            for unit in source_units.iterator():
                update_source_unit_index(writer, unit)
        finally:
            writer.close()

    # Update per language indices
    for lang in languages:
        language_units = units.filter(
            translation__language=lang
        ).exclude(
            target=''
        )

        if language_units.exists():
            index = get_target_index(lang.code)
            writer = BufferedWriter(index)
            try:

                for unit in language_units.iterator():
                    update_target_unit_index(writer, unit)
            finally:
                writer.close()


def add_index_update(unit_id, source, to_delete, language_code=''):
    from weblate.trans.models.search import IndexUpdate
    try:
        with transaction.atomic():
            IndexUpdate.objects.create(
                unitid=unit_id,
                source=source,
                to_delete=to_delete,
                language_code=language_code,
            )
    # pylint: disable=E0712
    except IntegrityError:
        try:
            update = IndexUpdate.objects.get(unitid=unit_id)
            if to_delete or source:
                if source:
                    update.source = True
                if to_delete:
                    update.to_delete = True
                    update.language_code = language_code
                update.save()
        except IndexUpdate.DoesNotExist:
            # It did exist, but was deleted meanwhile
            return


def update_index_unit(unit, source=True):
    '''
    Adds single unit to index.
    '''
    # Should this happen in background?
    if appsettings.OFFLOAD_INDEXING:
        add_index_update(unit.id, source, False)
        return

    # Update source
    if source:
        index = get_source_index()
        with AsyncWriter(index) as writer:
            update_source_unit_index(writer, unit)

    # Update target
    if unit.target:
        index = get_target_index(unit.translation.language.code)
        with AsyncWriter(index) as writer:
            update_target_unit_index(writer, unit)


def base_search(index, query, params, search, schema):
    '''
    Wrapper for fulltext search.
    '''
    with index.searcher() as searcher:
        queries = []
        for param in params:
            if search[param]:
                parser = qparser.QueryParser(param, schema)
                queries.append(
                    parser.parse(query)
                )
        terms = functools.reduce(lambda x, y: x | y, queries)
        return [result['pk'] for result in searcher.search(terms)]


def fulltext_search(query, lang, params):
    '''
    Performs fulltext search in given areas, returns set of primary keys.
    '''
    pks = set()

    search = {
        'source': False,
        'context': False,
        'target': False,
        'comment': False,
        'location': False,
    }
    search.update(params)

    if search['source'] or search['context'] or search['location']:
        pks.update(
            base_search(
                get_source_index(),
                query,
                ('source', 'context', 'location'),
                search,
                SourceSchema()
            )
        )

    if search['target'] or search['comment']:
        pks.update(
            base_search(
                get_target_index(lang),
                query,
                ('target', 'comment'),
                search,
                TargetSchema()
            )
        )

    return pks


def more_like(pk, source, top=5):
    '''
    Finds similar units.
    '''
    index = get_source_index()
    with index.searcher() as searcher:
        docnum = searcher.document_number(pk=pk)
        if docnum is None:
            return set()

        results = searcher.more_like(docnum, 'source', source, top)

        return set([result['pk'] for result in results])


def clean_search_unit(pk, lang):
    """Cleanups search index on unit deletion."""
    if appsettings.OFFLOAD_INDEXING:
        add_index_update(pk, False, True, lang)
    else:
        delete_search_unit(pk, lang)


def delete_search_unit(pk, lang):
    try:
        for index in (get_source_index(), get_target_index(lang)):
            with AsyncWriter(index) as writer:
                writer.delete_by_term('pk', pk)
    except IOError:
        return


def delete_search_units(source_units, languages):
    '''
    Delete fulltext index for given set of units.
    '''
    # Update source index
    index = get_source_index()
    writer = index.writer()
    try:
        for pk in source_units:
            writer.delete_by_term('pk', pk)
    finally:
        writer.commit()

    for lang, units in languages.items():
        index = get_target_index(lang)
        writer = index.writer()
        try:
            for pk in units:
                writer.delete_by_term('pk', pk)
        finally:
            writer.commit()
