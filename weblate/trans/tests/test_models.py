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
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
import shutil
import os
import git
from weblate.trans.models import (
    Project, SubProject
)


class RepoTestCase(TestCase):
    '''
    Generic class for tests working with repositories.
    '''
    def setUp(self):
        if 'test-repos' in settings.GIT_ROOT:
            test_dir = os.path.join(settings.GIT_ROOT, 'test')
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

        # Path where to clone remote repo for tests
        self.base_repo_path = os.path.join(
            settings.GIT_ROOT,
            'test-base-repo.git'
        )
        # Repository on which tests will be performed
        self.repo_path = os.path.join(
            settings.GIT_ROOT,
            'test-repo.git'
        )

        # Git command wrapper
        cmd = git.Git()

        # Clone repo for testing
        if not os.path.exists(self.base_repo_path):
            cmd.clone(
                '--bare',
                'git://github.com/nijel/weblate-test.git',
                self.base_repo_path
            )

        # Remove possibly existing directory
        if os.path.exists(self.repo_path):
            shutil.rmtree(self.repo_path)

        # Create repository copy for the test
        shutil.copytree(self.base_repo_path, self.repo_path)

        # Remove possibly existing project directory
        test_repo_path = os.path.join(settings.GIT_ROOT, 'test')
        if os.path.exists(test_repo_path):
            shutil.rmtree(test_repo_path)

    def create_project(self):
        '''
        Creates test project.
        '''
        return Project.objects.create(
            name='Test',
            slug='test',
            web='http://weblate.org/'
        )

    def create_subproject(self, file_format='auto', mask='po/*.po',
                          template=''):
        '''
        Creates test subproject.
        '''
        project = self.create_project()
        return SubProject.objects.create(
            name='Test',
            slug='test',
            project=project,
            repo=self.repo_path,
            push=self.repo_path,
            filemask=mask,
            template=template,
            file_format=file_format,
        )

    def create_iphone(self):
        return self.create_subproject(
            'strings',
            'iphone/*.lproj/Localizable.strings',
        )

    def create_android(self):
        return self.create_subproject(
            'aresource',
            'android/values-*/strings.xml',
            'android/values/strings.xml',
        )

    def create_java(self):
        return self.create_subproject(
            'properties',
            'java/swing_messages_*.properties',
            'java/swing_messages.properties',
        )

    def create_xliff(self):
        return self.create_subproject(
            'xliff',
            'xliff/*/DPH.xlf',
        )


class ProjectTest(RepoTestCase):
    '''
    Project object testing.
    '''
    def test_create(self):
        project = self.create_project()
        self.assertTrue(os.path.exists(project.get_path()))

    def test_validation(self):
        project = self.create_project()
        # Correct project
        project.full_clean()
        # Invalid commit message
        project.commit_message = '%(foo)s'
        self.assertRaisesMessage(
            ValidationError,
            'Bad format string',
            project.full_clean
        )

    def test_acl(self):
        '''
        Test for ACL handling.
        '''
        # Create user to verify ACL
        user = User.objects.create_user(
            username='testuser',
            password='testpassword'
        )

        # Create project
        project = self.create_project()

        # Enable ACL
        project.enable_acl = True
        project.save()

        # Check user does not have access
        self.assertFalse(project.has_acl(user))

        # Add ACL
        permission = Permission.objects.get(codename='weblate_acl_test')
        user.user_permissions.add(permission)

        # Need to fetch user again to clear permission cache
        user = User.objects.get(username='testuser')

        # We now should have access
        self.assertTrue(project.has_acl(user))


class SubProjectTest(RepoTestCase):
    '''
    SubProject object testing.
    '''
    def test_create(self):
        project = self.create_subproject()
        self.assertTrue(os.path.exists(project.get_path()))
        self.assertEqual(project.translation_set.count(), 2)

    def test_create_iphone(self):
        project = self.create_iphone()
        self.assertTrue(os.path.exists(project.get_path()))
        self.assertEqual(project.translation_set.count(), 1)

    def test_create_android(self):
        project = self.create_android()
        self.assertTrue(os.path.exists(project.get_path()))
        self.assertEqual(project.translation_set.count(), 1)

    def test_create_java(self):
        project = self.create_java()
        self.assertTrue(os.path.exists(project.get_path()))
        self.assertEqual(project.translation_set.count(), 1)

    def test_create_xliff(self):
        project = self.create_xliff()
        self.assertTrue(os.path.exists(project.get_path()))
        self.assertEqual(project.translation_set.count(), 1)

    def test_link(self):
        project = self.create_iphone()
        second = SubProject.objects.create(
            name='Test2',
            slug='test2',
            project=project.project,
            repo='weblate://test/test',
            filemask='po/*.po',
        )
        self.assertTrue(second.is_repo_link())
        self.assertEqual(second.translation_set.count(), 2)

    def test_validation(self):
        project = self.create_subproject()
        # Correct project
        project.full_clean()
        # Invalid mask
        project.filemask = 'foo/*.po'
        self.assertRaisesMessage(
            ValidationError,
            'The mask did not match any files!',
            project.full_clean
        )
        # Unknown file format
        project.filemask = 'iphone/*.lproj/Localizable.strings'
        self.assertRaisesMessage(
            ValidationError,
            'Format of 1 matched files could not be recognized.',
            project.full_clean
        )


class TranslationTest(RepoTestCase):
    '''
    Translation testing.
    '''
    def test_basic(self):
        project = self.create_subproject()
        translation = project.translation_set.get(language_code='cs')
        self.assertEqual(translation.translated, 0)
        self.assertEqual(translation.total, 4)
        self.assertEqual(translation.fuzzy, 0)
