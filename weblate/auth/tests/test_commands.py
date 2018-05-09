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

"""Test for user handling."""

from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError

from weblate.auth.models import User, Group
from weblate.trans.tests.utils import get_test_file, TempDirMixin


class CommandTest(TestCase, TempDirMixin):
    """Test for management commands."""
    def test_createadmin(self):
        call_command('createadmin')
        user = User.objects.get(username='admin')
        self.assertEqual(user.full_name, 'Weblate Admin')
        self.assertFalse(user.check_password('admin'))

    def test_createadmin_password(self):
        call_command('createadmin', password='admin')
        user = User.objects.get(username='admin')
        self.assertEqual(user.full_name, 'Weblate Admin')
        self.assertTrue(user.check_password('admin'))

    def test_createadmin_username(self):
        call_command('createadmin', username='admin2')
        user = User.objects.get(username='admin2')
        self.assertEqual(user.full_name, 'Weblate Admin')

    def test_createadmin_email(self):
        call_command('createadmin', email='noreply1@weblate.org')
        user = User.objects.get(username='admin')
        self.assertEqual(user.email, 'noreply1@weblate.org')

    def test_createadmin_twice(self):
        call_command('createadmin')
        self.assertRaises(
            CommandError,
            call_command,
            'createadmin'
        )

    def test_createadmin_update(self):
        call_command('createadmin', update=True)
        call_command('createadmin', update=True, password='123456')
        user = User.objects.get(username='admin')
        self.assertTrue(user.check_password('123456'))

    def test_importusers(self):
        # First import
        call_command('importusers', get_test_file('users.json'))

        # Test that second import does not change anything
        user = User.objects.get(username='weblate')
        user.full_name = 'Weblate test user'
        user.save()
        call_command('importusers', get_test_file('users.json'))
        user2 = User.objects.get(username='weblate')
        self.assertEqual(user.full_name, user2.full_name)

    def test_importdjangousers(self):
        # First import
        call_command('importusers', get_test_file('users-django.json'))
        self.assertEqual(User.objects.count(), 2)

    def test_import_empty_users(self):
        """Test importing empty file"""
        call_command('importusers', get_test_file('users-empty.json'))
        # Only anonymous user
        self.assertEqual(User.objects.count(), 1)

    def test_import_invalid_users(self):
        """Test error handling in user import"""
        call_command('importusers', get_test_file('users-invalid.json'))
        # Only anonymous user
        self.assertEqual(User.objects.count(), 1)

    def test_setupgroups(self):
        call_command('setupgroups')
        group = Group.objects.get(name='Users')
        self.assertTrue(
            group.roles.filter(name='Power user').exists()
        )
