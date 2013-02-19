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

"""
Tests for dictionary manipulations.
"""

from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.models import Dictionary
from django.core.urlresolvers import reverse
import os.path

TEST_DATA = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'data'
)
TEST_TBX = os.path.join(
    TEST_DATA,
    'terms.tbx'
)


class DictionaryTest(ViewTestCase):
    '''
    Testing of dictionary manipulations.
    '''

    def test_import(self):
        '''
        Test for importing of TBX into glossary.
        '''
        url_kwargs = {
            'lang': 'cs',
            'project': self.subproject.project.slug,
        }
        upload_url = reverse('upload_dictionary', kwargs=url_kwargs)
        show_url = reverse('show_dictionary', kwargs=url_kwargs)

        # Import file
        with open(TEST_TBX) as handle:
            response = self.client.post(upload_url, {'file': handle})

        # Check correct response
        self.assertRedirects(response, show_url)

        # Check number of imported objects
        self.assertEquals(Dictionary.objects.count(), 164)

        # Check they are shown
        response = self.client.get(show_url)
        self.assertContains(response, u'podpůrná vrstva')

    def test_add(self):
        '''
        Test for manually adding words to glossary.
        '''
        url_kwargs = {
            'lang': 'cs',
            'project': self.subproject.project.slug,
        }
        show_url = reverse('show_dictionary', kwargs=url_kwargs)

        # Add word
        response = self.client.post(
            show_url,
            {'source': 'source', 'target': u'překlad'}
        )

        # Check correct response
        self.assertRedirects(response, show_url)

        # Check number of imported objects
        self.assertEquals(Dictionary.objects.count(), 1)

        # Check they are shown
        response = self.client.get(show_url)
        self.assertContains(response, u'překlad')

