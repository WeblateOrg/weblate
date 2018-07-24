# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

import functools

from whoosh.fields import SchemaClass, TEXT, NUMERIC
from whoosh.query import Or, Term
from whoosh.writing import AsyncWriter, BufferedWriter
from whoosh import qparser

from django.conf import settings
from django.db.utils import IntegrityError
from django.utils.encoding import force_text
from django.db import transaction

from weblate.lang.models import Language
from weblate.utils.index import WhooshIndex


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

    def get_source_index(self):
        return self.open_index(SourceSchema, 'source')

    def get_target_index(self, lang):
        """Return target index object."""
        name = 'target-{0}'.format(lang)
        return self.open_index(TargetSchema, name)

    @staticmethod
    def update_source_unit_index(writer, unit):
        """Update source index for given unit."""
        writer.update_document(
            pk=unit.pk,
            source=force_text(unit.source),
            context=force_text(unit.context),
            location=force_text(unit.location),
        )

    @staticmethod
    def update_target_unit_index(writer, unit):
        """Update target index for given unit."""
        writer.update_document(
            pk=unit.pk,
            target=force_text(unit.target),
            comment=force_text(unit.comment),
        )

    def update_index(self, units):
        """Update fulltext index for given set of units."""
        languages = Language.objects.have_translation()

        # Update source index
        if units.exists():
            index = self.get_source_index()
            with BufferedWriter(index) as writer:
                for unit in units.iterator():
                    self.update_source_unit_index(writer, unit)

        # Update per language indices
        for lang in languages:
            language_units = units.filter(
                translation__language=lang
            ).exclude(
                target=''
            )

            if language_units.exists():
                index = self.get_target_index(lang.code)
                with BufferedWriter(index) as writer:
                    for unit in language_units.iterator():
                        self.update_target_unit_index(writer, unit)

    @staticmethod
    def add_index_update(unit_id, to_delete, language_code):
        from weblate.trans.models.search import IndexUpdate
        try:
            with transaction.atomic():
                IndexUpdate.objects.create(
                    unitid=unit_id,
                    to_delete=to_delete,
                    language_code=language_code,
                )
        except IntegrityError:
            try:
                update = IndexUpdate.objects.get(unitid=unit_id)
                if to_delete and not update.to_delete:
                    update.to_delete = True
                    update.save()
            except IndexUpdate.DoesNotExist:
                # It did exist, but was deleted meanwhile
                return

    @classmethod
    def update_index_unit(cls, unit):
        """Add single unit to index."""
        # Should this happen in background?
        if settings.OFFLOAD_INDEXING:
            cls.add_index_update(
                unit.id, False, unit.translation.language.code
            )
            return

        # Update source
        instance = cls()
        index = instance.get_source_index()
        with AsyncWriter(index) as writer:
            instance.update_source_unit_index(writer, unit)

        # Update target
        if unit.target:
            index = instance.get_target_index(unit.translation.language.code)
            with AsyncWriter(index) as writer:
                instance.update_target_unit_index(writer, unit)

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

            # Grab fulltext results
            results = [
                (h['pk'], h.score) for h in searcher.search(query, limit=top)
            ]
            if not results:
                return []
            # Normalize scores to 0-100
            max_score = max([h[1] for h in results])
            scores = {h[0]:  h[1] * 100 / max_score for h in results}

            # Filter results with score above 50 and not current unit
            return [h[0] for h in results if scores[h[0]] > 50 and h[0] != pk]

    def clean_search_unit(self, pk, lang):
        """Cleanup search index on unit deletion."""
        if settings.OFFLOAD_INDEXING:
            self.add_index_update(pk, True, lang)
        else:
            self.delete_search_unit(pk, lang)

    def delete_search_unit(self, pk, lang):
        try:
            indexes = (
                self.get_source_index(),
                self.get_target_index(lang)
            )
            for index in indexes:
                with AsyncWriter(index) as writer:
                    writer.delete_by_term('pk', pk)
        except IOError:
            return

    def delete_search_units(self, source_units, languages):
        """Delete fulltext index for given set of units."""
        # Update source index
        index = self.get_source_index()
        with index.writer() as writer:
            for pk in source_units:
                writer.delete_by_term('pk', pk)

        for lang, units in languages.items():
            index = self.get_target_index(lang)
            with index.writer() as writer:
                for pk in units:
                    writer.delete_by_term('pk', pk)
