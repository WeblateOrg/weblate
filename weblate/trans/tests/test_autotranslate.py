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
Tests for automatic translation
"""

from django.core.urlresolvers import reverse
from django.core.management import call_command
from django.core.management.base import CommandError

from weblate.trans.models import SubProject
from weblate.trans.tests.test_views import ViewTestCase


class AutoTranslationTest(ViewTestCase):
    def setUp(self):
        super(AutoTranslationTest, self).setUp()
        # Need extra power
        self.user.is_superuser = True
        self.user.save()
        self.subproject2 = SubProject.objects.create(
            name='Test 2',
            slug='test-2',
            project=self.project,
            repo=self.git_repo_path,
            push=self.git_repo_path,
            vcs='git',
            filemask='po/*.po',
            template='',
            file_format='po',
            new_base='',
            allow_translation_propagation=False,
        )

    def test_none(self):
        '''
        Tests for automatic translation with no content.
        '''
        url = reverse('auto_translation', kwargs=self.kw_translation)
        response = self.client.post(
            url
        )
        self.assertRedirects(response, self.translation_url)

    def make_different(self):
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )

    def perform_auto(self, expected=1, **kwargs):
        self.make_different()
        params = {'project': 'test', 'lang': 'cs', 'subproject': 'test-2'}
        url = reverse('auto_translation', kwargs=params)
        response = self.client.post(url, kwargs, follow=True)
        if expected == 1:
            self.assertContains(
                response,
                'Automatic translation completed, 1 string was updated.',
            )
        else:
            self.assertContains(
                response,
                'Automatic translation completed, no strings were updated.',
            )

        self.assertRedirects(response, reverse('translation', kwargs=params))
        # Check we've translated something
        translation = self.subproject2.translation_set.get(language_code='cs')
        self.assertEqual(translation.translated, expected)

    def test_different(self):
        '''
        Tests for automatic translation with different content.
        '''
        self.perform_auto()

    def test_inconsistent(self):
        self.perform_auto(0, inconsistent='1')

    def test_overwrite(self):
        self.perform_auto(overwrite='1')

    def test_command(self):
        call_command(
            'auto_translate',
            'test',
            'test',
            'cs',
        )

    def test_command_different(self):
        self.make_different()
        call_command(
            'auto_translate',
            'test',
            'test-2',
            'cs',
            source='test/test',
        )

    def test_command_errors(self):
        self.assertRaises(
            CommandError,
            call_command,
            'auto_translate',
            'test',
            'test',
            'cs',
            user='invalid',
        )
        self.assertRaises(
            CommandError,
            call_command,
            'auto_translate',
            'test',
            'test',
            'cs',
            source='invalid',
        )
        self.assertRaises(
            CommandError,
            call_command,
            'auto_translate',
            'test',
            'test',
            'cs',
            source='test/invalid',
        )
        self.assertRaises(
            CommandError,
            call_command,
            'auto_translate',
            'test',
            'test',
            'xxx',
        )
