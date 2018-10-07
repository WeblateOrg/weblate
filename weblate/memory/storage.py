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
from django.utils.translation import pgettext, ugettext as _


from translate.misc.xml_helpers import getXMLlang, getXMLspace
from translate.storage.tmx import tmxfile

from whoosh.fields import SchemaClass, TEXT, ID, STORED, NUMERIC
from whoosh import qparser
from whoosh import query

from weblate.lang.models import Language
from weblate.utils.errors import report_error
from weblate.utils.index import WhooshIndex
from weblate.utils.search import Comparer


class MemoryImportError(Exception):
    pass


def get_node_data(unit, node):
    """Generic implementation of LISAUnit.gettarget."""
    # The language should be present as xml:lang, but in some
    # cases it's there only as lang
    return (
        getXMLlang(node) or node.get('lang'),
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

    @staticmethod
    def get_language_code(code, langmap):
        language = Language.objects.auto_get_or_create(code)
        if langmap and language.code in langmap:
            language = Language.objects.auto_get_or_create(
                langmap[language.code]
            )
        return language.code

    @staticmethod
    def get_category(category=None, project=None, user=None):
        if project:
            return CATEGORY_PRIVATE_OFFSET + project.pk
        if user:
            return CATEGORY_USER_OFFSET + user.pk
        return category

    @classmethod
    def import_file(cls, fileobj, langmap=None, category=None, project=None,
                    user=None):
        origin = force_text(os.path.basename(fileobj.name)).lower()
        category = cls.get_category(category, project, user)
        name, extension = os.path.splitext(origin)
        if len(name) > 25:
            origin = '{}...{}'.format(name[:25], extension)
        if extension == '.tmx':
            result = cls.import_tmx(fileobj, langmap, category, origin)
        elif extension == '.json':
            result = cls.import_json(fileobj, category, origin)
        else:
            raise MemoryImportError(_('Unsupported file!'))
        if not result:
            raise MemoryImportError(
                _('No valid entries found in the uploaded file!')
            )
        return result

    @classmethod
    def import_json(cls, fileobj, category=None, origin=None):
        from weblate.memory.tasks import update_memory_task
        content = fileobj.read()
        try:
            data = json.loads(force_text(content))
        except (ValueError, UnicodeDecodeError) as error:
            report_error(error)
            raise MemoryImportError(_('Failed to parse JSON file!'))
        updates = {}
        fields = cls.SCHEMA().names()
        if category:
            updates = {
                'category': category,
                'origin': origin,
            }
        found = 0
        if isinstance(data, list):
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                # Apply overrides
                entry.update(updates)
                # Ensure all fields are set
                for field in fields:
                    if not entry.get(field):
                        continue
                # Ensure there are not extra fields
                record = {field: entry[field] for field in fields}
                update_memory_task.delay(**record)
                found += 1
        return found

    @classmethod
    def import_tmx(cls, fileobj, langmap=None, category=None, origin=None):
        from weblate.memory.tasks import update_memory_task
        if category is None:
            category = CATEGORY_FILE
        try:
            storage = tmxfile.parsefile(fileobj)
        except SyntaxError as error:
            report_error(error)
            raise MemoryImportError(_('Failed to parse TMX file!'))
        header = next(
            storage.document.getroot().iterchildren(
                storage.namespaced("header")
            )
        )
        source_language_code = header.get('srclang')
        source_language = cls.get_language_code(source_language_code, langmap)

        languages = {}
        found = 0
        for unit in storage.units:
            # Parse translations (translate-toolkit does not care about
            # languages here, it just picks first and second XML elements)
            translations = {}
            for node in unit.getlanguageNodes():
                lang, text = get_node_data(unit, node)
                if not lang or not text:
                    continue
                translations[lang] = text
                if lang not in languages:
                    languages[lang] = cls.get_language_code(lang, langmap)

            try:
                source = translations.pop(source_language_code)
            except KeyError:
                # Skip if source language is not present
                continue

            for lang, text in translations.items():
                update_memory_task.delay(
                    source_language=source_language,
                    target_language=languages[lang],
                    source=source,
                    target=text,
                    origin=origin,
                    category=category,
                )
                found += 1
        return found

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

    def list_documents(self, user=None, project=None):
        catfilter = self.get_filter(user, project, False, False)
        self.open_searcher()
        return self.searcher.search(catfilter, limit=None)

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

    def delete(self, origin=None, category=None, project=None, user=None):
        """Delete entries based on filter."""
        category = self.get_category(category, project, user)
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
