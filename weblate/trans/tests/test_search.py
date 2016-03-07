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

"""
Tests for search views.
"""

from __future__ import unicode_literals

import re
import shutil
import tempfile
import os.path
from unittest import TestCase
from whoosh.filedb.filestore import FileStorage
from whoosh.fields import Schema, ID, TEXT
from django.core.urlresolvers import reverse
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests import OverrideSettings
from weblate.trans.search import update_index_unit, fulltext_search
import weblate.trans.search
from weblate.trans.models import IndexUpdate


class SearchViewTest(ViewTestCase):
    def setUp(self):
        super(SearchViewTest, self).setUp()
        self.translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        self.translate_url = self.translation.get_translate_url()

    def do_search(self, params, expected, url=None):
        '''
        Helper method for performing search test.
        '''
        if url is None:
            url = self.translate_url
        response = self.client.get(url, params)
        if expected is None:
            self.assertRedirects(
                response,
                self.translation.get_absolute_url()
            )
        else:
            self.assertContains(
                response,
                expected
            )
        return response

    def test_all_search(self):
        '''
        Searching in all projects.
        '''
        response = self.client.get(
            reverse('search'),
            {'q': 'hello'}
        )
        self.assertContains(
            response,
            '<span class="hlmatch">Hello</span>, world'
        )
        response = self.client.get(
            reverse('search'),
            {'q': 'hello', 'type': 'untranslated'}
        )
        self.assertContains(
            response,
            '<span class="hlmatch">Hello</span>, world'
        )
        response = self.client.get(
            reverse('search'),
            {'q': 'hello', 'type': 'todo'}
        )
        self.assertContains(
            response,
            '<span class="hlmatch">Hello</span>, world'
        )
        response = self.client.get(
            reverse('search'),
            {'q': 'hello', 'type': 'nottranslated'}
        )
        self.assertContains(
            response,
            '<span class="hlmatch">Hello</span>, world'
        )
        response = self.client.get(
            reverse('search'),
            {'type': 'php_format'}
        )
        self.assertContains(
            response,
            'No matching strings found!'
        )
        response = self.client.get(
            reverse('search'),
            {'type': 'php_format', 'ignored': '1'}
        )
        self.assertContains(
            response,
            'No matching strings found!'
        )
        response = self.client.get(
            reverse('search'),
            {'type': 'xxx'}
        )
        self.assertContains(
            response,
            'xxx is not one of the available choices.'
        )

    def test_pagination(self):
        response = self.client.get(
            reverse('search'),
            {'q': 'hello', 'page': 1}
        )
        self.assertContains(
            response,
            '<span class="hlmatch">Hello</span>, world'
        )
        response = self.client.get(
            reverse('search'),
            {'q': 'hello', 'page': 10}
        )
        self.assertContains(
            response,
            '<span class="hlmatch">Hello</span>, world'
        )
        response = self.client.get(
            reverse('search'),
            {'q': 'hello', 'page': 'x'}
        )
        self.assertContains(
            response,
            '<span class="hlmatch">Hello</span>, world'
        )

    def test_language_search(self):
        '''
        Searching in all projects.
        '''
        response = self.client.get(
            reverse('search'),
            {'q': 'hello', 'lang': 'cs'}
        )
        self.assertContains(
            response,
            '<span class="hlmatch">Hello</span>, world'
        )

    def test_project_search(self):
        '''
        Searching within project.
        '''
        # Default
        self.do_search(
            {'q': 'hello'},
            'Fulltext search for'
        )
        # Fulltext
        self.do_search(
            {'q': 'hello', 'search': 'ftx'},
            'Fulltext search for'
        )
        # Substring
        self.do_search(
            {'q': 'hello', 'search': 'substring'},
            'Substring search for'
        )
        # Exact string
        self.do_search(
            {'q': 'Thank you for using Weblate.', 'search': 'exact'},
            'Search for exact string'
        )
        # Short string
        self.do_search(
            {'q': 'x'},
            'Ensure this value has at least 2 characters (it has 1).'
        )
        # Wrong type
        self.do_search(
            {'q': 'xxxxx', 'search': 'xxxx'},
            'Select a valid choice. xxxx is not one of the available choices.'
        )

    def test_review(self):
        # Review
        self.do_search(
            {'date': '2010-01-10', 'type': 'review'},
            None
        )
        # Review, invalid date
        self.do_search(
            {'date': '2010-01-', 'type': 'review'},
            'Enter a valid date.'
        )

    def test_search_links(self):
        response = self.do_search(
            {'q': 'Weblate', 'search': 'substring'},
            'Substring search for'
        )
        # Extract search ID
        search_id = re.findall(
            r'sid=([0-9a-f-]*)&amp',
            response.content.decode('utf-8')
        )[0]
        # Try access to pages
        response = self.client.get(
            self.translate_url,
            {'sid': search_id, 'offset': 0}
        )
        self.assertContains(
            response,
            'http://demo.weblate.org/',
        )
        response = self.client.get(
            self.translate_url,
            {'sid': search_id, 'offset': 1}
        )
        self.assertContains(
            response,
            'Thank you for using Weblate.',
        )
        # Invalid offset
        response = self.client.get(
            self.translate_url,
            {'sid': search_id, 'offset': 'bug'}
        )
        self.assertContains(
            response,
            'http://demo.weblate.org/',
        )
        # Go to end
        response = self.client.get(
            self.translate_url,
            {'sid': search_id, 'offset': 2}
        )
        self.assertRedirects(
            response,
            self.translation.get_absolute_url()
        )
        # Try invalid SID (should be deleted above)
        response = self.client.get(
            self.translate_url,
            {'sid': search_id, 'offset': 1}
        )
        self.assertRedirects(
            response,
            self.translation.get_absolute_url()
        )

    def test_invalid_sid(self):
        response = self.client.get(
            self.translate_url,
            {'sid': 'invalid'}
        )
        self.assertRedirects(
            response,
            self.translation.get_absolute_url()
        )

    def test_mixed_sid(self):
        """
        Tests using SID from other translation.
        """
        translation = self.subproject.translation_set.get(
            language_code='de'
        )
        response = self.do_search(
            {'q': 'Weblate', 'search': 'substring'},
            'Substring search for',
            url=translation.get_translate_url()
        )
        search_id = re.findall(
            r'sid=([0-9a-f-]*)&amp',
            response.content.decode('utf-8')
        )[0]
        response = self.client.get(
            self.translate_url,
            {'sid': search_id, 'offset': 0}
        )
        self.assertRedirects(
            response,
            self.translation.get_absolute_url()
        )

    def test_search_checksum(self):
        unit = self.translation.unit_set.get(
            source='Try Weblate at <http://demo.weblate.org/>!\n'
        )
        response = self.do_search(
            {'checksum': unit.checksum},
            '3 / 4'
        )
        # Extract search ID
        search_id = re.findall(
            r'sid=([0-9a-f-]*)&amp',
            response.content.decode('utf-8')
        )[0]
        # Navigation
        response = self.do_search(
            {'sid': search_id, 'offset': 0},
            '1 / 4'
        )
        response = self.do_search(
            {'sid': search_id, 'offset': 3},
            '4 / 4'
        )
        response = self.do_search(
            {'sid': search_id, 'offset': 4},
            None
        )

    def test_search_type(self):
        self.do_search(
            {'type': 'untranslated'},
            'Strings needing action',
        )
        self.do_search(
            {'type': 'fuzzy'},
            None
        )
        self.do_search(
            {'type': 'suggestions'},
            None
        )
        self.do_search(
            {'type': 'allchecks'},
            None
        )
        self.do_search(
            {'type': 'plurals'},
            None
        )
        self.do_search(
            {'type': 'all'},
            '1 / 4'
        )

    def test_search_errors(self):
        self.do_search(
            {'type': 'nonexisting-type'},
            'nonexisting-type is not one of the available choices'
        )
        self.do_search(
            {'date': 'nonexisting'},
            'date: Enter a valid date.'
        )

    def test_search_plural(self):
        response = self.do_search(
            {'q': 'banana'},
            'banana'
        )
        self.assertContains(response, 'One')
        self.assertContains(response, 'Few')
        self.assertContains(response, 'Other')
        self.assertNotContains(response, 'Plural form ')

    def test_checksum(self):
        response = self.do_search({'checksum': 'invalid'}, None)
        self.assertRedirects(
            response,
            self.get_translation().get_absolute_url()
        )


class SearchBackendTest(ViewTestCase):
    def do_index_update(self):
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        unit = self.get_translation().unit_set.get(
            source='Hello, world!\n',
        )
        #
        update_index_unit(unit, False)
        update_index_unit(unit, True)
        update_index_unit(unit, True)

    @OverrideSettings(OFFLOAD_INDEXING=False)
    def test_add(self):
        self.do_index_update()
        self.assertEqual(IndexUpdate.objects.count(), 0)

    @OverrideSettings(OFFLOAD_INDEXING=True)
    def test_add_offload(self):
        self.do_index_update()
        self.assertEqual(IndexUpdate.objects.count(), 1)
        update = IndexUpdate.objects.all()[0]
        self.assertTrue(update.source, True)


class SearchMigrationTest(TestCase):
    """Search index migration testing"""
    def setUp(self):
        self.path = tempfile.mkdtemp()
        self.backup = weblate.trans.search.STORAGE
        self.storage = FileStorage(self.path)
        weblate.trans.search.STORAGE = self.storage
        self.storage.create()

    def tearDown(self):
        if os.path.exists(self.path):
            shutil.rmtree(self.path)
        weblate.trans.search.STORAGE = self.backup

    def do_test(self, source, target):
        if source is not None:
            self.storage.create_index(source, 'source')
        if target is not None:
            self.storage.create_index(target, 'target-cs')

        sindex = weblate.trans.search.get_source_index()
        self.assertIsNotNone(sindex)
        tindex = weblate.trans.search.get_target_index('cs')
        self.assertIsNotNone(tindex)
        writer = sindex.writer()
        writer.update_document(
            pk=1,
            source="source",
            context="context",
            location="location",
        )
        writer.commit()
        writer = tindex.writer()
        writer.update_document(
            pk=1,
            target="target",
            comment="comment"
        )
        writer.commit()
        for item in ('source', 'context', 'location', 'target'):
            self.assertEqual(
                fulltext_search(item, 'cs', {item: True}),
                set([1])
            )

    def test_nonexisting(self):
        self.do_test(None, None)

    def test_nonexisting_dir(self):
        shutil.rmtree(self.path)
        self.do_test(None, None)

    def test_current(self):
        source = weblate.trans.search.SourceSchema
        target = weblate.trans.search.TargetSchema
        self.do_test(source, target)

    def test_2_4(self):
        source = Schema(
            checksum=ID(stored=True, unique=True),
            source=TEXT(),
            context=TEXT(),
            location=TEXT()
        )
        target = Schema(
            checksum=ID(stored=True, unique=True),
            target=TEXT(),
            comment=TEXT(),
        )
        self.do_test(source, target)

    def test_2_1(self):
        source = Schema(
            checksum=ID(stored=True, unique=True),
            source=TEXT(),
            context=TEXT(),
        )
        target = Schema(
            checksum=ID(stored=True, unique=True),
            target=TEXT(),
        )
        self.do_test(source, target)
