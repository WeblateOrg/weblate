# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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
Tests for locking.
"""

from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.models.subproject import SubProject
from django.core.urlresolvers import reverse


class LockTest(ViewTestCase):
    def setUp(self):
        super(LockTest, self).setUp()

        # Need extra power
        self.user.is_superuser = True
        self.user.save()

    def assertComponentLocked(self):
        subproject = SubProject.objects.get(
            slug=self.subproject.slug,
            project__slug=self.project.slug,
        )
        self.assertTrue(subproject.locked)
        response = self.client.get(
            reverse('subproject', kwargs=self.kw_subproject)
        )
        self.assertContains(
            response,
            'This translation is currently locked for updates!'
        )

    def assertComponentNotLocked(self):
        subproject = SubProject.objects.get(
            slug=self.subproject.slug,
            project__slug=self.project.slug,
        )
        self.assertFalse(subproject.locked)
        response = self.client.get(
            reverse('subproject', kwargs=self.kw_subproject)
        )
        self.assertNotContains(
            response,
            'This translation is currently locked for updates!'
        )

    def test_subproject(self):
        response = self.client.get(
            reverse('lock_subproject', kwargs=self.kw_subproject)
        )
        self.assertRedirects(
            response,
            reverse('subproject', kwargs=self.kw_subproject)
        )
        self.assertComponentLocked()

        response = self.client.get(
            reverse('unlock_subproject', kwargs=self.kw_subproject)
        )
        self.assertRedirects(
            response,
            reverse('subproject', kwargs=self.kw_subproject)
        )
        self.assertComponentNotLocked()

    def test_project(self):
        response = self.client.get(
            reverse('lock_project', kwargs=self.kw_project)
        )
        self.assertRedirects(
            response,
            reverse('project', kwargs=self.kw_project)
        )
        self.assertComponentLocked()

        response = self.client.get(
            reverse('subproject', kwargs=self.kw_subproject)
        )
        self.assertContains(
            response,
            'This translation is currently locked for updates!'
        )

        response = self.client.get(
            reverse('unlock_project', kwargs=self.kw_project)
        )
        self.assertRedirects(
            response,
            reverse('project', kwargs=self.kw_project)
        )
        self.assertComponentNotLocked()

    def test_translation(self):
        response = self.client.get(
            reverse('lock_translation', kwargs=self.kw_translation)
        )
        self.assertRedirects(
            response,
            reverse('translation', kwargs=self.kw_translation)
        )
        self.assertTrue(self.get_translation().is_user_locked())

        response = self.client.get(
            reverse('unlock_translation', kwargs=self.kw_translation)
        )
        self.assertRedirects(
            response,
            reverse('translation', kwargs=self.kw_translation)
        )
        self.assertFalse(self.get_translation().is_user_locked())

        response = self.client.get(
            reverse('js-lock', kwargs=self.kw_translation)
        )
        self.assertFalse(self.get_translation().is_user_locked())
