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
Tests for translation models.
"""

from django.test import TestCase
from django.conf import settings
import shutil
import os
from weblate.trans.models import (
    Project, SubProject
)


class RepoTestCase(TestCase):
    '''
    Generic class for tests working with repositories.
    '''
    def setUp(self):
        if 'test-repos' in settings.GIT_ROOT:
            if os.path.exists(settings.GIT_ROOT):
                shutil.rmtree(settings.GIT_ROOT)

    def create_project(self):
        '''
        Creates test project.
        '''
        return Project.objects.create(
            name='Test',
            slug='test',
            web='http://weblate.org/'
        )

    def create_subproject(self):
        '''
        Creates test subproject.
        '''
        project = self.create_project()
        return SubProject.objects.create(
            name='Test',
            slug='test',
            project=project,
            repo='git://github.com/nijel/weblate-test.git',
            filemask='po/*.po',
        )


class ProjectTest(RepoTestCase):
    '''
    Project object testing.
    '''
    def test_create(self):
        project = self.create_project()
        self.assertTrue(os.path.exists(project.get_path()))


class SubProjectTest(RepoTestCase):
    '''
    SubProject object testing.
    '''
    def test_create(self):
        project = self.create_subproject()
        self.assertTrue(os.path.exists(project.get_path()))
