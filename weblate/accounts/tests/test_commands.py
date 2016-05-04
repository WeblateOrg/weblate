# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
Tests for user handling.
"""

import tempfile
from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.core.management.base import CommandError

from weblate.trans.tests.utils import get_test_file
from weblate.accounts.models import Profile


class CommandTest(TestCase):
    '''
    Tests for management commands.
    '''
    def test_createadmin(self):
        call_command('createadmin')
        user = User.objects.get(username='admin')
        self.assertEqual(user.first_name, 'Weblate Admin')
        self.assertEqual(user.last_name, '')
        self.assertFalse(user.check_password('admin'))

    def test_createadmin_password(self):
        call_command('createadmin', password='admin')
        user = User.objects.get(username='admin')
        self.assertEqual(user.first_name, 'Weblate Admin')
        self.assertEqual(user.last_name, '')
        self.assertTrue(user.check_password('admin'))

    def test_setupgroups(self):
        call_command('setupgroups')
        group = Group.objects.get(name='Users')
        self.assertTrue(
            group.permissions.filter(
                codename='save_translation'
            ).exists()
        )
        call_command('setupgroups', move=True)

    def test_importusers(self):
        # First import
        call_command('importusers', get_test_file('users.json'))

        # Test that second import does not change anything
        user = User.objects.get(username='weblate')
        user.first_name = 'Weblate test user'
        user.save()
        call_command('importusers', get_test_file('users.json'))
        user2 = User.objects.get(username='weblate')
        self.assertEqual(user.first_name, user2.first_name)

    def test_importdjangousers(self):
        # First import
        call_command('importusers', get_test_file('users-django.json'))
        self.assertEqual(User.objects.count(), 2)

    def test_import_empty_users(self):
        """Test importing empty file"""
        call_command('importusers', get_test_file('users-empty.json'))
        # Only anonymous user
        self.assertEqual(User.objects.count(), 1)

    def test_import_invalud_users(self):
        """Test error handling in user import"""
        call_command('importusers', get_test_file('users-invalid.json'))
        # Only anonymous user
        self.assertEqual(User.objects.count(), 1)

    def test_userdata(self):
        # Create test user
        user = User.objects.create_user('testuser', 'test@example.com', 'x')
        user.profile.translated = 1000
        user.profile.save()

        with tempfile.NamedTemporaryFile() as output:
            call_command('dumpuserdata', output.name)
            call_command('importuserdata', output.name)

        profile = Profile.objects.get(user__username='testuser')
        self.assertEqual(profile.translated, 2000)

    def test_changesite(self):
        call_command('changesite', get_name=True)
        self.assertNotEqual(Site.objects.get(pk=1).domain, 'test.weblate.org')
        call_command('changesite', set_name='test.weblate.org')
        self.assertEqual(Site.objects.get(pk=1).domain, 'test.weblate.org')

    def test_changesite_new(self):
        self.assertRaises(
            CommandError,
            call_command,
            'changesite', get_name=True, site_id=2
        )
        call_command('changesite', set_name='test.weblate.org', site_id=2)
        self.assertEqual(Site.objects.get(pk=2).domain, 'test.weblate.org')
