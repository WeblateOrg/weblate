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
from weblate.trans.permissions import check_owner


class PermissionsTest(TestCase):
    def test_owner(self):
        user = User.objects.create_user('user', 'test@example.com', 'x')
        owner = User.objects.create_user('owner', 'test@example.com', 'x')
        owner.groups.add(Group.objects.get(name='Owners'))
        project = Project.objects.create(slug='test', owner=owner)
        self.assertTrue(check_owner(owner, project, 'trans.author_translation'))
        self.assertFalse(check_owner(owner, project, 'trans.delete_translation'))
        self.assertFalse(check_owner(user, project, 'trans.author_translation'))
