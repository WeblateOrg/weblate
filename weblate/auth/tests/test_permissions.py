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

from django.test import TestCase

from weblate.auth.models import User
from weblate.trans.models import Project, Comment


class PermissionsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'user', 'test@example.com', 'x'
        )
        self.admin = User.objects.create_user(
            'admin', 'admin@example.com', 'x'
        )
        self.superuser = User.objects.create_user(
            'super', 'super@example.com', 'x',
            is_superuser=True
        )

        self.project = Project.objects.create(slug='test')
        self.project.add_user(self.admin, '@Administration')

    def test_admin_perm(self):
        self.assertTrue(
            self.superuser.has_perm('upload.authorship', self.project)
        )
        self.assertTrue(
            self.admin.has_perm('upload.authorship', self.project)
        )
        self.assertFalse(
            self.user.has_perm('upload.authorship', self.project)
        )

    def test_user_perm(self):
        self.assertTrue(
            self.superuser.has_perm('comment.add', self.project)
        )
        self.assertTrue(
            self.admin.has_perm('comment.add', self.project)
        )
        self.assertTrue(
            self.user.has_perm('comment.add', self.project)
        )

    def test_delete_comment(self):
        comment = Comment(project=self.project)
        self.assertTrue(
            self.superuser.has_perm('comment.delete', comment, self.project)
        )
        self.assertTrue(
            self.admin.has_perm('comment.delete', comment, self.project)
        )
        self.assertFalse(
            self.user.has_perm('comment.delete', comment, self.project)
        )

    def test_delete_owned_comment(self):
        comment = Comment(project=self.project, user=self.user)
        self.assertTrue(
            self.superuser.has_perm('comment.delete', comment, self.project)
        )
        self.assertTrue(
            self.admin.has_perm('comment.delete', comment, self.project)
        )
        self.assertTrue(
            self.user.has_perm('comment.delete', comment, self.project)
        )

    def test_delete_not_owned_comment(self):
        comment = Comment(project=self.project, user=self.admin)
        self.assertTrue(
            self.superuser.has_perm('comment.delete', comment, self.project)
        )
        self.assertTrue(
            self.admin.has_perm('comment.delete', comment, self.project)
        )
        self.assertFalse(
            self.user.has_perm('comment.delete', comment, self.project)
        )
