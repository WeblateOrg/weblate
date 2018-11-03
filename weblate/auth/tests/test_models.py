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

from django.contrib.auth.models import Group as DjangoGroup

from weblate.auth.data import SELECTION_MANUAL, SELECTION_ALL
from weblate.auth.models import Group, Role, User
from weblate.lang.models import Language
from weblate.trans.models import Project, ComponentList
from weblate.trans.tests.test_views import FixtureTestCase


class ModelTest(FixtureTestCase):
    def setUp(self):
        super(ModelTest, self).setUp()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.translation = self.get_translation()
        self.group = Group.objects.create(
            name='Test',
            language_selection=SELECTION_ALL,
        )
        self.group.projects.add(self.project)

    def test_project(self):
        # No permissions
        self.assertFalse(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm('unit.edit', self.translation))

        # Access permission on adding to group
        self.user.clear_cache()
        self.user.groups.add(self.group)
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm('unit.edit', self.translation))

        # Translate permission on adding role to group
        self.user.clear_cache()
        self.group.roles.add(Role.objects.get(name='Power user'))
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertTrue(self.user.has_perm('unit.edit', self.translation))

    def test_componentlist(self):
        # Add user to group of power users
        self.user.groups.add(self.group)
        self.group.roles.add(Role.objects.get(name='Power user'))

        # Assign component list to a group
        clist = ComponentList.objects.create(name='Test', slug='test')
        self.group.componentlist = clist
        self.group.save()

        # No permissions as component list is empty
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm('unit.edit', self.translation))

        # Permissions should exist after adding to a component list
        self.user.clear_cache()
        clist.components.add(self.component)
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertTrue(self.user.has_perm('unit.edit', self.translation))

    def test_languages(self):
        # Add user to group with german language
        self.user.groups.add(self.group)
        self.group.language_selection = SELECTION_MANUAL
        self.group.save()
        self.group.roles.add(Role.objects.get(name='Power user'))
        self.group.languages.set(
            Language.objects.filter(code='de'), clear=True
        )

        # Permissions should deny access
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertFalse(self.user.has_perm('unit.edit', self.translation))

        # Adding Czech language should unlock it
        self.user.clear_cache()
        self.group.languages.add(Language.objects.get(code='cs'))
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertTrue(self.user.has_perm('unit.edit', self.translation))

    def test_groups(self):
        # Add test group
        self.user.groups.add(self.group)
        self.assertEqual(self.user.groups.count(), 3)

        # Add same named Django group
        self.user.groups.add(DjangoGroup.objects.create(name='Test'))
        self.assertEqual(self.user.groups.count(), 3)

        # Add different Django group
        self.user.groups.add(DjangoGroup.objects.create(name='Second'))
        self.assertEqual(self.user.groups.count(), 4)

        # Remove Weblate group
        self.user.groups.remove(Group.objects.get(name='Test'))
        self.assertEqual(self.user.groups.count(), 3)

        # Remove Django group
        self.user.groups.remove(DjangoGroup.objects.get(name='Second'))
        self.assertEqual(self.user.groups.count(), 2)

    def test_user(self):
        # Create user with Django User fields
        user = User.objects.create(
            first_name='First',
            last_name='Last',
            is_staff=True,
            is_superuser=True
        )
        self.assertEqual(user.full_name, 'First Last')
        self.assertEqual(user.is_superuser, True)
