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

import os.path

from django.utils.encoding import force_text

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

    def import_tmx(self, fileobj, langmap=None):
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
                        category=CATEGORY_FILE,
                    )

    def lookup(self, source_language, target_language, text):
        langfilter = query.And([
            query.Term('source_language', source_language),
            query.Term('target_language', target_language),
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
                match['source'], match['target'], similarity, match['origin']
            )

    def delete(self, origin):
        """Delete entries by origin."""
        with self.writer() as writer:
            return writer.delete_by_term('origin', origin)

    def empty(self):
        """Recreates translation memory."""
        self.cleanup()
        self.index = self.open_index()
        self.searcher = None

    def get_origins(self):
        self.open_searcher()
        return [
            force_text(x) for x in self.searcher.lexicon('origin')
        ]
