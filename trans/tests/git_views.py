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
Tests for Git manipulation views.
"""

from trans.tests.views import ViewTestCase
from django.core.urlresolvers import reverse


class GitNoChangeTest(ViewTestCase):
    '''
    Testing of git manipulations with no change in repo.
    '''

    STATUS_CHECK = 'Push changes to remote repository'

    def setUp(self):
        super(GitNoChangeTest, self).setUp()
        # We need extra privileges for overwriting
        self.user.is_superuser = True
        self.user.save()

    def test_project_commit(self):
        response = self.client.get(
            reverse('commit_project', kwargs=self.kw_project)
        )
        self.assertRedirects(response, self.project_url)

    def test_subproject_commit(self):
        response = self.client.get(
            reverse('commit_subproject', kwargs=self.kw_subproject)
        )
        self.assertRedirects(response, self.subproject_url)

    def test_translation_commit(self):
        response = self.client.get(
            reverse('commit_translation', kwargs=self.kw_translation)
        )
        self.assertRedirects(response, self.translation_url)

    def test_project_update(self):
        response = self.client.get(
            reverse('update_project', kwargs=self.kw_project)
        )
        self.assertRedirects(response, self.project_url)

    def test_subproject_update(self):
        response = self.client.get(
            reverse('update_subproject', kwargs=self.kw_subproject)
        )
        self.assertRedirects(response, self.subproject_url)

    def test_translation_update(self):
        response = self.client.get(
            reverse('update_translation', kwargs=self.kw_translation)
        )
        self.assertRedirects(response, self.translation_url)

    def test_project_push(self):
        response = self.client.get(
            reverse('push_project', kwargs=self.kw_project)
        )
        self.assertRedirects(response, self.project_url)

    def test_subproject_push(self):
        response = self.client.get(
            reverse('push_subproject', kwargs=self.kw_subproject)
        )
        self.assertRedirects(response, self.subproject_url)

    def test_translation_push(self):
        response = self.client.get(
            reverse('push_translation', kwargs=self.kw_translation)
        )
        self.assertRedirects(response, self.translation_url)

    def test_project_reset(self):
        response = self.client.get(
            reverse('reset_project', kwargs=self.kw_project)
        )
        self.assertRedirects(response, self.project_url)

    def test_subproject_reset(self):
        response = self.client.get(
            reverse('reset_subproject', kwargs=self.kw_subproject)
        )
        self.assertRedirects(response, self.subproject_url)

    def test_translation_reset(self):
        response = self.client.get(
            reverse('reset_translation', kwargs=self.kw_translation)
        )
        self.assertRedirects(response, self.translation_url)

    def test_project_status(self):
        response = self.client.get(
            reverse('git_status_project', kwargs=self.kw_project)
        )
        self.assertContains(response, self.STATUS_CHECK)

    def test_subproject_status(self):
        response = self.client.get(
            reverse('git_status_subproject', kwargs=self.kw_subproject)
        )
        self.assertContains(response, self.STATUS_CHECK)

    def test_translation_status(self):
        response = self.client.get(
            reverse('git_status_translation', kwargs=self.kw_translation)
        )
        self.assertContains(response, self.STATUS_CHECK)


class GitChangeTest(GitNoChangeTest):
    '''
    Testing of git manipulations with not commited change in repo.
    '''

    STATUS_CHECK = 'There are some not commited changes!'

    def setUp(self):
        super(GitChangeTest, self).setUp()
        self.change_unit(u'Ahoj světe!\n')


class GitCommitedChangeTest(GitNoChangeTest):
    '''
    Testing of git manipulations with commited change in repo.
    '''

    STATUS_CHECK = 'There are some new commits in local Git repository!'

    def setUp(self):
        super(GitCommitedChangeTest, self).setUp()
        self.change_unit(u'Ahoj světe!\n')
        self.project.commit_pending()
