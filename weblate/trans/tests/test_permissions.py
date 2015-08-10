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

from django.contrib.auth.models import User, Group
from django.test import TestCase
from weblate.trans.models import Project
from weblate.trans.permissions import (
    check_owner, check_permission, can_delete_comment
)


class PermissionsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('user', 'test@example.com', 'x')
        self.owner = User.objects.create_user('owner', 'test@example.com', 'x')
        self.owner.groups.add(Group.objects.get(name='Owners'))
        self.project = Project.objects.create(slug='test')
        self.project.owners.add(self.owner)

    def test_owner_owned(self):
        self.assertTrue(
            check_owner(self.owner, self.project, 'trans.author_translation')
        )

    def test_owner_no_perm(self):
        self.assertFalse(
            check_owner(self.owner, self.project, 'trans.delete_translation')
        )

    def test_owner_user(self):
        self.assertFalse(
            check_owner(self.user, self.project, 'trans.author_translation')
        )

    def test_check_owner(self):
        self.assertTrue(
            check_permission(
                self.owner, self.project, 'trans.author_translation'
            )
        )

    def test_check_user(self):
        self.assertFalse(
            check_permission(
                self.user, self.project, 'trans.author_translation'
            )
        )

    def test_delete_comment_owner(self):
        self.assertTrue(can_delete_comment(self.owner, self.project))

    def test_delete_comment_user(self):
        self.assertFalse(can_delete_comment(self.user, self.project))

    def test_cache(self):
        key = ('can_delete_comment', self.user.id)
        self.assertNotIn(key, self.project.permissions_cache)
        self.assertFalse(can_delete_comment(self.user, self.project))
        self.assertFalse(self.project.permissions_cache[key])
        self.project.permissions_cache[key] = True
        self.assertTrue(can_delete_comment(self.user, self.project))
