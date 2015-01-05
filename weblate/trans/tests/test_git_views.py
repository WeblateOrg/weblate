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
Tests for Git manipulation views.
"""

from weblate.trans.tests.test_views import ViewTestCase
from django.core.urlresolvers import reverse


class GitNoChangeProjectTest(ViewTestCase):
    '''
    Testing of git manipulations with no change in repo.
    '''

    STATUS_CHECK = 'Push changes to the remote repository'
    TEST_TYPE = 'project'

    def setUp(self):
        super(GitNoChangeProjectTest, self).setUp()
        # We need extra privileges for overwriting
        self.user.is_superuser = True
        self.user.save()

    def get_test_url(self, prefix):
        return reverse(
            '%s_%s' % (prefix, self.TEST_TYPE),
            kwargs=getattr(self, 'kw_%s' % self.TEST_TYPE)
        )

    def get_expected_redirect(self):
        return getattr(self, '%s_url' % self.TEST_TYPE) + '#repository'

    def test_commit(self):
        response = self.client.get(
            self.get_test_url('commit')
        )
        self.assertRedirects(response, self.get_expected_redirect())

    def test_update(self):
        response = self.client.get(
            self.get_test_url('update')
        )
        self.assertRedirects(response, self.get_expected_redirect())

    def test_project_push(self):
        response = self.client.get(
            self.get_test_url('push')
        )
        self.assertRedirects(response, self.get_expected_redirect())

    def test_project_reset(self):
        response = self.client.get(
            self.get_test_url('reset')
        )
        self.assertRedirects(response, self.get_expected_redirect())

    def test_project_status(self):
        response = self.client.get(
            self.get_test_url('git_status')
        )
        self.assertContains(response, self.STATUS_CHECK)


class GitNoChangeSubProjectTest(GitNoChangeProjectTest):
    '''
    Testing of subproject git manipulations.
    '''
    TEST_TYPE = 'subproject'


class GitNoChangeTranslationTest(GitNoChangeProjectTest):
    '''
    Testing of translation git manipulations.
    '''
    TEST_TYPE = 'translation'


class GitChangeProjectTest(GitNoChangeProjectTest):
    '''
    Testing of project git manipulations with not committed change in repo.
    '''

    STATUS_CHECK = 'There are some not committed changes!'

    def setUp(self):
        super(GitChangeProjectTest, self).setUp()
        self.change_unit(u'Ahoj světe!\n')


class GitChangeSubProjectTest(GitChangeProjectTest):
    '''
    Testing of subproject git manipulations with not committed change in repo.
    '''
    TEST_TYPE = 'subproject'


class GitChangeTranslationTest(GitChangeProjectTest):
    '''
    Testing of translation git manipulations with not committed change in repo.
    '''
    TEST_TYPE = 'translation'


class GitCommittedChangeProjectTest(GitNoChangeProjectTest):
    '''
    Testing of project git manipulations with committed change in repo.
    '''

    STATUS_CHECK = 'There are some new commits in the local repository!'

    def setUp(self):
        super(GitCommittedChangeProjectTest, self).setUp()
        self.change_unit(u'Ahoj světe!\n')
        self.project.commit_pending(self.get_request('/'))


class GitCommittedChangeSubProjectTest(GitCommittedChangeProjectTest):
    '''
    Testing of subproject git manipulations with committed change in repo.
    '''
    TEST_TYPE = 'subproject'


class GitCommittedChangeTranslationTest(GitCommittedChangeProjectTest):
    '''
    Testing of translation git manipulations with committed change in repo.
    '''
    TEST_TYPE = 'translation'
