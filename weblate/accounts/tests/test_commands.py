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

import os.path

from django.test import TestCase
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.core.management.base import CommandError

from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.trans.tests.utils import TempDirMixin
from weblate.accounts.models import Profile


class CommandTest(TestCase, TempDirMixin):
    """Test for management commands."""
    def test_userdata(self):
        # Create test user
        language = Language.objects.get(code='cs')
        user = User.objects.create_user('testuser', 'test@example.com', 'x')
        user.profile.translated = 1000
        user.profile.languages.add(language)
        user.profile.secondary_languages.add(language)
        user.profile.save()

        try:
            self.create_temp()
            output = os.path.join(self.tempdir, 'users.json')
            call_command('dumpuserdata', output)

            user.profile.languages.clear()
            user.profile.secondary_languages.clear()

            call_command('importuserdata', output)
        finally:
            self.remove_temp()

        profile = Profile.objects.get(user__username='testuser')
        self.assertEqual(profile.translated, 2000)
        self.assertTrue(
            profile.languages.filter(code='cs').exists()
        )
        self.assertTrue(
            profile.secondary_languages.filter(code='cs').exists()
        )

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
