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

"""Test for search views."""

from __future__ import unicode_literals

import re
import shutil
from unittest import TestCase
from whoosh.filedb.filestore import FileStorage
from django.urls import reverse
from django.test.utils import override_settings
from django.http import QueryDict

from weblate.accounts.ratelimit import reset_rate_limit
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.search import Fulltext
from weblate.trans.models import IndexUpdate
from weblate.trans.tests.utils import TempDirMixin
from weblate.utils.state import STATE_FUZZY, STATE_TRANSLATED


class SearchViewTest(ViewTestCase):
    def setUp(self):
        super(SearchViewTest, self).setUp()
        self.translation = self.component.translation_set.get(
            language_code='cs'
        )
        self.translate_url = self.translation.get_translate_url()
        self.update_fulltext_index()
        reset_rate_limit('search', address='127.0.0.1')

    def do_search(self, params, expected, url=None):
        """Helper method for performing search test."""
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

    def do_search_url(self, url):
        """Test search on given URL."""
        response = self.client.get(url, {'q': 'hello'})
        self.assertContains(
            response,
            '<span class="hlmatch">Hello</span>, world'
        )
        response = self.client.get(url, {'date': '2010-01-10'})
        self.assertContains(response, '2010-01-10')

    @override_settings(AUTH_MAX_ATTEMPTS=20000)
    def test_all_search(self):
        """Searching in all projects."""
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
            'No matching strings found.'
        )
        response = self.client.get(
            reverse('search'),
            {'type': 'php_format', 'ignored': '1'}
        )
        self.assertContains(
            response,
            'No matching strings found.'
        )
        response = self.client.get(
            reverse('search'),
            {'type': 'xxx'}
        )
        self.assertContains(response, 'Please choose a valid filter type.')
        self.do_search_url(reverse('search'))

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
        """Searching in all projects."""
        response = self.client.get(
            reverse('search'),
            {'q': 'hello', 'lang': 'cs'}
        )
        self.assertContains(
            response,
            '<span class="hlmatch">Hello</span>, world'
        )

    def test_project_search(self):
        """Searching within project."""
        self.do_search_url(reverse('search', kwargs=self.kw_project))

    def test_component_search(self):
        """Searching within component."""
        self.do_search_url(reverse('search', kwargs=self.kw_component))

    def test_project_language_search(self):
        """Searching within project."""
        self.do_search_url(
            reverse(
                'search',
                kwargs={'project': self.project.slug, 'lang': 'cs'}
            )
        )

    def test_translation_search(self):
        """Searching within translation."""
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
            'The query string has to be longer!',
        )
        # Short exact
        self.do_search(
            {'q': 'x', 'search': 'exact'},
            None
        )
        # Wrong type
        self.do_search(
            {'q': 'Thank', 'search': 'xxxx'},
            'Please choose a valid search type.'
        )

    def test_random(self):
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        self.do_search(
            {'type': 'random'},
            'Nazdar svete'
        )
        self.do_search(
            {'type': 'random', 'q': 'hello'},
            'Nazdar svete'
        )

    def test_review(self):
        # Review
        self.do_search(
            {'date': '2010-01-10', 'type': 'all'},
            None
        )
        self.do_search(
            {'date': '2010-01-10', 'type': 'all', 'exclude_user': 'testuser'},
            None
        )
        self.do_search(
            {'date': '2010-01-10', 'type': 'all', 'only_user': 'testuser'},
            None
        )
        self.do_search(
            {'only_user': 'testuser'},
            None
        )
        # Review, invalid date
        self.do_search(
            {'date': '2010-01-', 'type': 'all'},
            'Enter a valid date.'
        )

    def extract_params(self, response):
        search_url = re.findall(
            r'data-params="([^"]*)"',
            response.content.decode('utf-8')
        )[0]
        return QueryDict(search_url, mutable=True)

    def test_search_links(self):
        response = self.do_search(
            {'q': 'Weblate', 'search': 'substring'},
            'Substring search for'
        )
        # Extract search URL
        params = self.extract_params(response)
        # Try access to pages
        params['offset'] = 1
        response = self.client.get(self.translate_url, params)
        self.assertContains(response, 'https://demo.weblate.org/')
        params['offset'] = 2
        response = self.client.get(self.translate_url, params)
        self.assertContains(response, 'Thank you for using Weblate.')
        # Invalid offset
        params['offset'] = 'bug'
        response = self.client.get(self.translate_url, params)
        self.assertContains(response, 'https://demo.weblate.org/')
        # Go to end
        params['offset'] = 3
        response = self.client.get(self.translate_url, params)
        self.assertRedirects(
            response,
            self.translation.get_absolute_url()
        )
        # Try no longer cached query (should be deleted above)
        params['offset'] = 2
        response = self.client.get(self.translate_url, params)
        self.assertContains(
            response,
            'Thank you for using Weblate.',
        )

    def test_search_checksum(self):
        unit = self.translation.unit_set.get(
            source='Try Weblate at <https://demo.weblate.org/>!\n'
        )
        response = self.do_search(
            {'checksum': unit.checksum},
            '3 / 4'
        )
        # Extract search ID
        params = self.extract_params(response)
        # Navigation
        params['offset'] = 1
        response = self.do_search(params, '1 / 4')
        params['offset'] = 4
        response = self.do_search(params, '4 / 4')
        params['offset'] = 5
        response = self.do_search(params, None)

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
            {'type': 'check:plurals'},
            None
        )
        self.do_search(
            {'type': 'all'},
            '1 / 4'
        )

    def test_search_errors(self):
        self.do_search(
            {'type': 'nonexisting-type'},
            'Please choose a valid filter type.',
        )
        self.do_search(
            {'date': 'nonexisting'},
            'Enter a valid date.'
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
        self.do_search(
            {'checksum': 'invalid'},
            'Invalid checksum specified!'
        )


class SearchBackendTest(ViewTestCase):
    def setUp(self):
        super(SearchBackendTest, self).setUp()
        self.update_fulltext_index()

    def do_index_update(self):
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        unit = self.get_translation().unit_set.get(
            source='Hello, world!\n',
        )
        Fulltext.update_index_unit(unit)
        Fulltext.update_index_unit(unit)

    @override_settings(OFFLOAD_INDEXING=False)
    def test_add(self):
        self.do_index_update()
        self.assertEqual(IndexUpdate.objects.count(), 0)

    @override_settings(OFFLOAD_INDEXING=True)
    def test_add_offload(self):
        self.do_index_update()
        self.assertEqual(IndexUpdate.objects.count(), 1)
        update = IndexUpdate.objects.all()[0]
        self.assertTrue(update.source, True)


class SearchMigrationTest(TestCase, TempDirMixin):
    """Search index migration testing"""
    def setUp(self):
        self.create_temp()
        self.storage = FileStorage(self.tempdir)
        self.storage.create()

    def tearDown(self):
        self.remove_temp()

    def do_test(self):
        fulltext = Fulltext()
        fulltext.storage = self.storage

        sindex = fulltext.get_source_index()
        self.assertIsNotNone(sindex)
        tindex = fulltext.get_target_index('cs')
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
                fulltext.search(item, ['cs'], {item: True}),
                set([1])
            )

    def test_nonexisting(self):
        self.do_test()

    def test_nonexisting_dir(self):
        shutil.rmtree(self.tempdir)
        self.tempdir = None
        self.do_test()


class ReplaceTest(ViewTestCase):
    """Test for search and replace functionality."""

    def setUp(self):
        super(ReplaceTest, self).setUp()
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        self.unit = self.get_unit()

    def do_replace_test(self, url, confirm=True):
        response = self.client.post(
            url,
            {
                'search': 'Nazdar',
                'replacement': 'Ahoj',
            },
            follow=True
        )
        self.assertContains(
            response,
            'Please review and confirm the search and replace results.'
        )
        payload = {
            'search': 'Nazdar',
            'replacement': 'Ahoj',
            'confirm': '1',
        }
        if confirm:
            payload['units'] = self.unit.pk
        response = self.client.post(url, payload, follow=True)
        unit = self.get_unit()
        if confirm:
            self.assertContains(
                response,
                'Search and replace completed, 1 string was updated.'
            )
            self.assertEqual(unit.target, 'Ahoj svete!\n')
        else:
            self.assertContains(
                response,
                'Search and replace completed, no strings were updated.'
            )
            self.assertEqual(unit.target, 'Nazdar svete!\n')

    def test_no_match(self):
        response = self.client.post(
            reverse('replace', kwargs=self.kw_translation),
            {
                'search': 'Ahoj',
                'replacement': 'Cau',
            },
            follow=True
        )
        self.assertContains(
            response,
            'Search and replace completed, no strings were updated.'
        )
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Nazdar svete!\n')

    def test_replace(self):
        self.do_replace_test(
            reverse('replace', kwargs=self.kw_translation),
        )

    def test_replace_project(self):
        self.do_replace_test(
            reverse('replace', kwargs=self.kw_project),
        )

    def test_replace_component(self):
        self.do_replace_test(
            reverse('replace', kwargs=self.kw_component),
        )


class MassStateTest(ViewTestCase):
    """Test for mass state change functionality."""

    def setUp(self):
        super(MassStateTest, self).setUp()
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n',
            fuzzy=True,
        )
        self.unit = self.get_unit()
        self.make_manager()

    def do_mass_state_test(self, url, confirm=True):
        response = self.client.post(
            url,
            {
                'type': 'fuzzy',
                'state': STATE_TRANSLATED,
            },
            follow=True
        )
        unit = self.get_unit()
        self.assertContains(
            response,
            'Mass state change completed, 1 string was updated.'
        )
        self.assertEqual(unit.state, STATE_TRANSLATED)

    def test_no_match(self):
        response = self.client.post(
            reverse('state-change', kwargs=self.kw_project),
            {
                'type': 'approved',
                'state': STATE_FUZZY,
            },
            follow=True
        )
        self.assertContains(
            response,
            'Mass state change completed, no strings were updated.'
        )
        unit = self.get_unit()
        self.assertEqual(unit.state, STATE_FUZZY)

    def test_mass_state(self):
        self.do_mass_state_test(
            reverse('state-change', kwargs=self.kw_translation),
        )

    def test_mass_state_project(self):
        self.do_mass_state_test(
            reverse('state-change', kwargs=self.kw_project),
        )

    def test_mass_state_component(self):
        self.do_mass_state_test(
            reverse('state-change', kwargs=self.kw_component),
        )
