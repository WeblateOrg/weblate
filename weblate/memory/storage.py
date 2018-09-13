# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

import json
import os.path

from django.utils.encoding import force_text
from django.utils.translation import pgettext


from translate.misc.xml_helpers import getXMLlang, getXMLspace
from translate.storage.tmx import tmxfile

from whoosh.fields import SchemaClass, TEXT, ID, STORED, NUMERIC
from whoosh import qparser
from whoosh import query

from weblate.lang.models import Language
from weblate.utils.index import WhooshIndex
from weblate.utils.search import Comparer


def get_node_data(unit, node):
    """Generic implementation of LISAUnit.gettarget."""
    return (
        getXMLlang(node),
        unit.getNodeText(node, getXMLspace(unit.xmlelement, 'preserve'))
    )


CATEGORY_FILE = 1
CATEGORY_SHARED = 2
CATEGORY_PRIVATE_OFFSET = 10000000
CATEGORY_USER_OFFSET = 20000000


def get_category_name(category, origin):
    if CATEGORY_PRIVATE_OFFSET < category < CATEGORY_USER_OFFSET:
        text = pgettext('Translation memory category', 'Project: {}')
    elif CATEGORY_USER_OFFSET < category:
        text = pgettext('Translation memory category', 'Personal: {}')
    elif category == CATEGORY_SHARED:
        text = pgettext('Translation memory category', 'Shared: {}')
    elif category == CATEGORY_FILE:
        text = pgettext('Translation memory category', 'File: {}')
    else:
        text = 'Category {}: {{}}'.format(category)
    return text.format(origin)


class TMSchema(SchemaClass):
    """Fultext index schema for source and context strings."""
    source_language = ID(stored=True)
    target_language = ID(stored=True)
    source = TEXT(stored=True)
    target = STORED()
    origin = ID(stored=True)
    category = NUMERIC(stored=True)


class TranslationMemory(WhooshIndex):
    LOCATION = 'memory'
    SCHEMA = TMSchema

    def __init__(self):
        self.index = self.open_index()
        self.parser = qparser.QueryParser(
            'source',
            schema=self.index.schema,
            group=qparser.OrGroup.factory(0.9),
            termclass=query.FuzzyTerm,
        )
        self.searcher = None
        self.comparer = Comparer()

    def __del__(self):
        self.close()

    def open_searcher(self):
        if self.searcher is None:
            self.searcher = self.index.searcher()

    def doc_count(self):
        self.open_searcher()
        return self.searcher.doc_count()

    def close(self):
        if self.searcher is not None:
            self.searcher.close()
            self.searcher = None

    def writer(self):
        return self.index.writer()

    def get_language_code(self, code, langmap):
        language = Language.objects.auto_get_or_create(code)
        if langmap and language.code in langmap:
            language = Language.objects.auto_get_or_create(
                langmap[language.code]
            )
        return language.code

    def import_tmx(self, fileobj, langmap=None, category=CATEGORY_FILE):
        origin = force_text(os.path.basename(fileobj.name))
        storage = tmxfile.parsefile(fileobj)
        header = next(
            storage.document.getroot().iterchildren(
                storage.namespaced("header")
            )
        )
        source_language_code = header.get('srclang')
        source_language = self.get_language_code(source_language_code, langmap)

        languages = {}
        with self.writer() as writer:
            for unit in storage.units:
                # Parse translations (translate-toolkit does not care about
                # languages here, it just picks first and second XML elements)
                translations = {}
                for node in unit.getlanguageNodes():
                    lang, text = get_node_data(unit, node)
                    translations[lang] = text
                    if lang not in languages:
                        languages[lang] = self.get_language_code(lang, langmap)

                try:
                    source = translations.pop(source_language_code)
                except KeyError:
                    # Skip if source language is not present
                    continue

                for lang, text in translations.items():
                    writer.add_document(
                        source_language=source_language,
                        target_language=languages[lang],
                        source=source,
                        target=text,
                        origin=origin,
                        category=category,
                    )

    @staticmethod
    def get_filter(user, project, use_shared, use_file):
        """Create query to filter categories based on selection."""
        # Always include file imported memory
        if use_file:
            category_filter = [query.Term('category', CATEGORY_FILE)]
        else:
            category_filter = []
        # Per user memory
        if user:
            category_filter.append(
                query.Term('category', CATEGORY_USER_OFFSET + user.id)
            )
        # Private project memory
        if project:
            category_filter.append(
                query.Term('category', CATEGORY_PRIVATE_OFFSET + project.id)
            )
        # Shared memory
        if use_shared:
            category_filter.append(query.Term('category', CATEGORY_SHARED))
        return query.Or(category_filter)

    def lookup(self, source_language, target_language, text, user,
               project, use_shared):
        langfilter = query.And([
            query.Term('source_language', source_language),
            query.Term('target_language', target_language),
            self.get_filter(user, project, use_shared, True),
        ])
        self.open_searcher()
        text_query = self.parser.parse(text)
        matches = self.searcher.search(
            text_query, filter=langfilter, limit=20000
        )

        for match in matches:
            similarity = self.comparer.similarity(text, match['source'])
            if similarity < 30:
                continue
            yield (
                match['source'], match['target'], similarity,
                match['category'], match['origin']
            )

    def delete(self, origin, category):
        """Delete entries by origin."""
        with self.writer() as writer:
            if origin:
                return writer.delete_by_term('origin', origin)
            return writer.delete_by_term('category', category)

    def empty(self):
        """Recreates translation memory."""
        self.cleanup()
        self.index = self.open_index()
        self.searcher = None

    def get_values(self, field):
        self.open_searcher()
        return [
            force_text(x) for x in self.searcher.reader().field_terms(field)
        ]

    def dump(self, handle, indent=2):
        """Dump memory content to JSON file."""
        self.open_searcher()
        json.dump(
            list(self.searcher.documents()),
            handle,
            indent=indent,
        )
