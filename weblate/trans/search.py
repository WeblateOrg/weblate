# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Whoosh based full text search."""

from __future__ import absolute_import, unicode_literals

from collections import defaultdict
import functools
import logging
from time import sleep

from celery_batches import Batches

from whoosh.fields import SchemaClass, TEXT, NUMERIC
from whoosh.query import Or, Term
from whoosh.index import LockError
from whoosh import qparser

from django.utils.encoding import force_text

from weblate.celery import app
from weblate.utils.celery import extract_batch_args, extract_batch_kwargs
from weblate.utils.index import WhooshIndex

LOGGER = logging.getLogger('weblate.search')


class TargetSchema(SchemaClass):
    """Fultext index schema for target strings."""
    pk = NUMERIC(stored=True, unique=True)
    target = TEXT()
    comment = TEXT()


class SourceSchema(SchemaClass):
    """Fultext index schema for source and context strings."""
    pk = NUMERIC(stored=True, unique=True)
    source = TEXT()
    context = TEXT()
    location = TEXT()


class Fulltext(WhooshIndex):
    LOCATION = 'whoosh'
    FAKE = False

    def get_source_index(self):
        return self.open_index(SourceSchema, 'source')

    def get_target_index(self, lang):
        """Return target index object."""
        name = 'target-{0}'.format(lang)
        return self.open_index(TargetSchema, name)

    @staticmethod
    def update_source_unit_index(writer, searcher, unit):
        """Update source index for given unit."""
        if not isinstance(unit, dict):
            unit = {
                'source': unit.source,
                'context': unit.context,
                'location': unit.location,
                'pk': unit.pk,
            }
        writer.delete_by_term('pk', unit['pk'], searcher)
        writer.add_document(
            pk=unit['pk'],
            source=force_text(unit['source']),
            context=force_text(unit['context']),
            location=force_text(unit['location']),
        )

    @staticmethod
    def update_target_unit_index(writer, searcher, unit):
        """Update target index for given unit."""
        if not isinstance(unit, dict):
            unit = {
                'pk': unit.pk,
                'target': unit.target,
                'comment': unit.comment,
            }
        writer.delete_by_term('pk', unit['pk'], searcher)
        writer.add_document(
            pk=unit['pk'],
            target=force_text(unit['target']),
            comment=force_text(unit['comment']),
        )

    def update_index(self, units):
        """Update fulltext index for given set of units."""

        # Update source index
        index = self.get_source_index()
        with index.writer() as writer:
            with writer.searcher() as searcher:
                for unit in units:
                    self.update_source_unit_index(writer, searcher, unit)

        languages = set([unit['language'] for unit in units])

        # Update per language indices
        for language in languages:
            index = self.get_target_index(language)
            with index.writer() as writer:
                with writer.searcher() as searcher:
                    for unit in units:
                        if unit['language'] != language:
                            continue
                        self.update_target_unit_index(writer, searcher, unit)

    @classmethod
    def update_index_unit(cls, unit):
        """Add single unit to index."""
        if not cls.FAKE:
            update_fulltext.delay(
                pk=unit.pk,
                source=force_text(unit.source),
                context=force_text(unit.context),
                location=force_text(unit.location),
                target=force_text(unit.target),
                comment=force_text(unit.comment),
                language=force_text(unit.translation.language.code),
            )

    @staticmethod
    def base_search(index, query, params, search, schema):
        """Wrapper for fulltext search."""
        with index.searcher() as searcher:
            queries = []
            for param in params:
                if search[param]:
                    parser = qparser.QueryParser(param, schema)
                    queries.append(
                        parser.parse(query)
                    )
            terms = functools.reduce(lambda x, y: x | y, queries)
            return [
                result['pk'] for result in searcher.search(terms, limit=None)
            ]

    def search(self, query, langs, params):
        """Perform fulltext search in given areas.

        Returns set of primary keys.
        """
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
                self.base_search(
                    self.get_source_index(),
                    query,
                    ('source', 'context', 'location'),
                    search,
                    SourceSchema()
                )
            )

        if search['target'] or search['comment']:
            for lang in langs:
                pks.update(
                    self.base_search(
                        self.get_target_index(lang),
                        query,
                        ('target', 'comment'),
                        search,
                        TargetSchema()
                    )
                )

        return pks

    def more_like(self, pk, source, top=5):
        """Find similar units."""
        index = self.get_source_index()
        with index.searcher() as searcher:
            # Extract key terms
            kts = searcher.key_terms_from_text(
                'source', source,
                numterms=10,
                normalize=False
            )
            # Create an Or query from the key terms
            query = Or(
                [Term('source', word, boost=weight) for word, weight in kts]
            )
            LOGGER.debug('more like query: %r', query)

            # Grab fulltext results
            results = [
                (h['pk'], h.score) for h in searcher.search(query, limit=top)
            ]
            LOGGER.debug('found %d matches', len(results))
            if not results:
                return []

            # Filter bad results
            threshold = max([h[1] for h in results]) / 2
            results = [h[0] for h in results if h[1] > threshold]
            LOGGER.debug(
                'filter %d matches over threshold %d', len(results), threshold
            )

            return results

    @classmethod
    def clean_search_unit(cls, pk, lang):
        """Cleanup search index on unit deletion."""
        if not cls.FAKE:
            delete_fulltext.delay(pk, lang)

    @staticmethod
    def delete_units_index(index, units):
        with index.writer() as writer:
            with writer.searcher() as searcher:
                for pk in units:
                    writer.delete_by_term('pk', pk, searcher)

    def delete_search_units(self, source_units, languages):
        """Delete fulltext index for given set of units."""
        # Update source index
        self.delete_units_index(
            self.get_source_index(),
            source_units
        )

        for lang, units in languages.items():
            self.delete_units_index(
                self.get_target_index(lang),
                units
            )


@app.task(base=Batches, flush_every=1000, flush_interval=300, bind=True)
def update_fulltext(self, *args, **kwargs):
    unitdata = extract_batch_kwargs(*args, **kwargs)
    fulltext = Fulltext()

    # Update index
    try:
        fulltext.update_index(unitdata)
    except LockError:
        LOGGER.info('retrying update batch of len %d', len(unitdata))
        # Manually handle retries, it doesn't work
        # with celery-batches
        sleep(10)
        for unit in unitdata:
            update_fulltext.delay(**unit)


@app.task(base=Batches, flush_every=1000, flush_interval=300, bind=True)
def delete_fulltext(self, *args):
    ids = extract_batch_args(*args)
    fulltext = Fulltext()

    units = set()
    languages = defaultdict(set)
    for unit, language in ids:
        units.add(unit)
        if language is None:
            continue
        languages[language].add(unit)

    try:
        fulltext.delete_search_units(units, languages)
    except LockError:
        LOGGER.info('retrying delete batch of len %d', len(ids))
        # Manually handle retries, it doesn't work
        # with celery-batches
        sleep(10)
        for unit in ids:
            delete_fulltext.delay(*unit)
