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

"""Test for management views."""

import os.path
import shutil

from django.urls import reverse

from weblate.trans.models import Project, Component, WhiteboardMessage
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.data import data_dir


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


class RenameTest(ViewTestCase):
    def test_denied(self):
        self.assertNotContains(
            self.client.get(reverse('project', kwargs=self.kw_project)),
            '#rename',
        )
        self.assertNotContains(
            self.client.get(reverse('component', kwargs=self.kw_component)),
            '#rename',
        )
        response = self.client.post(
            reverse('rename', kwargs=self.kw_project),
            {'slug': 'xxxx'}
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse('rename', kwargs=self.kw_component),
            {'slug': 'xxxx'}
        )
        self.assertEqual(response.status_code, 403)

        other = Project.objects.create(name='Other', slug='other')
        response = self.client.post(
            reverse('move', kwargs=self.kw_component),
            {'project': other.pk}
        )
        self.assertEqual(response.status_code, 403)

    def test_move_component(self):
        self.make_manager()
        other = Project.objects.create(name='Other project', slug='other')
        self.assertContains(
            self.client.get(reverse('component', kwargs=self.kw_component)),
            'Other project',
        )
        response = self.client.post(
            reverse('move', kwargs=self.kw_component),
            {'project': other.pk}
        )
        self.assertRedirects(response, '/projects/other/test/')
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.project.slug, 'other')
        self.assertIsNotNone(component.repository.last_remote_revision)

    def test_rename_component(self):
        self.make_manager()
        self.assertContains(
            self.client.get(reverse('component', kwargs=self.kw_component)),
            '#rename',
        )
        response = self.client.post(
            reverse('rename', kwargs=self.kw_component),
            {'slug': 'xxxx'}
        )
        self.assertRedirects(response, '/projects/test/xxxx/')
        component = Component.objects.get(pk=self.component.pk)
        self.assertEqual(component.slug, 'xxxx')
        self.assertIsNotNone(component.repository.last_remote_revision)
        response = self.client.get(component.get_absolute_url())
        self.assertContains(response, '/projects/test/xxxx/')

    def test_rename_project(self):
        # Remove stale dir from previous tests
        target = os.path.join(data_dir('vcs'), 'xxxx')
        if os.path.exists(target):
            shutil.rmtree(target)
        self.make_manager()
        self.assertContains(
            self.client.get(reverse('project', kwargs=self.kw_project)),
            '#rename',
        )
        response = self.client.post(
            reverse('rename', kwargs=self.kw_project),
            {'slug': 'xxxx'}
        )
        self.assertRedirects(response, '/projects/xxxx/')
        project = Project.objects.get(pk=self.project.pk)
        self.assertEqual(project.slug, 'xxxx')
        for component in project.component_set.all():
            self.assertIsNotNone(component.repository.last_remote_revision)
            response = self.client.get(component.get_absolute_url())
            self.assertContains(response, '/projects/xxxx/')


class WhiteboardTest(ViewTestCase):
    data = {'message': 'Whiteboard testing', 'category': 'warning'}

    def perform_test(self, url):
        response = self.client.post(url, self.data, follow=True)
        self.assertEqual(response.status_code, 403)
        self.make_manager()
        response = self.client.post(url, self.data, follow=True)
        self.assertContains(response, self.data['message'])

    def test_translation(self):
        kwargs = {'lang': 'cs'}
        kwargs.update(self.kw_component)
        url = reverse('whiteboard_translation', kwargs=kwargs)
        self.perform_test(url)

    def test_component(self):
        url = reverse('whiteboard_component', kwargs=self.kw_component)
        self.perform_test(url)

    def test_project(self):
        url = reverse('whiteboard_project', kwargs=self.kw_project)
        self.perform_test(url)

    def test_delete(self):
        self.test_project()
        message = WhiteboardMessage.objects.all()[0]
        self.client.post(
            reverse('whiteboard-delete', kwargs={'pk': message.pk})
        )
        self.assertEqual(WhiteboardMessage.objects.count(), 0)

    def test_delete_deny(self):
        message = WhiteboardMessage.objects.create(message='test')
        self.client.post(
            reverse('whiteboard-delete', kwargs={'pk': message.pk})
        )
        self.assertEqual(WhiteboardMessage.objects.count(), 1)
