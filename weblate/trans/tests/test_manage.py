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

"""Test for management views."""

from django.urls import reverse

from weblate.trans.tests.test_views import ViewTestCase


class RemovalTest(ViewTestCase):
    def test_translation(self):
        self.make_manager()
        kwargs = {'lang': 'cs'}
        kwargs.update(self.kw_component)
        url = reverse('remove_translation', kwargs=kwargs)
        response = self.client.post(url, {'confirm': ''}, follow=True)
        self.assertContains(
            response,
            'The translation name does not match the one to delete!'
        )
        response = self.client.post(
            url, {'confirm': 'test/test/cs'}, follow=True
        )
        self.assertContains(
            response,
            'Translation has been removed.',
        )

    def test_component(self):
        self.make_manager()
        url = reverse('remove_component', kwargs=self.kw_component)
        response = self.client.post(url, {'confirm': ''}, follow=True)
        self.assertContains(
            response,
            'The translation name does not match the one to delete!'
        )
        response = self.client.post(url, {'confirm': 'test/test'}, follow=True)
        self.assertContains(
            response,
            'component has been removed.',
        )

    def test_project(self):
        self.make_manager()
        url = reverse('remove_project', kwargs=self.kw_project)
        response = self.client.post(url, {'confirm': ''}, follow=True)
        self.assertContains(
            response,
            'The translation name does not match the one to delete!'
        )
        response = self.client.post(url, {'confirm': 'test'}, follow=True)
        self.assertContains(
            response,
            'Project has been removed.',
        )
