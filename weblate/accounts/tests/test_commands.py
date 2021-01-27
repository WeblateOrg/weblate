#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

import os

from django.core.management import call_command
from django.test import TestCase

from weblate.accounts.models import Profile
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.trans.models import Project
from weblate.trans.tests.utils import TempDirMixin, get_test_file

USERDATA_JSON = get_test_file("userdata.json")


class CommandTest(TestCase, TempDirMixin):
    """Test for management commands."""

    def test_userdata(self):
        # Create test user
        language = Language.objects.get(code="cs")
        user = User.objects.create_user("testuser", "test@example.com", "x")
        user.profile.translated = 1000
        user.profile.languages.add(language)
        user.profile.secondary_languages.add(language)
        user.profile.save()
        user.profile.watched.add(Project.objects.create(name="name", slug="name"))

        try:
            self.create_temp()
            output = os.path.join(self.tempdir, "users.json")
            call_command("dumpuserdata", output)

            user.profile.languages.clear()
            user.profile.secondary_languages.clear()

            call_command("importuserdata", output)
        finally:
            self.remove_temp()

        profile = Profile.objects.get(user__username="testuser")
        self.assertEqual(profile.translated, 2000)
        self.assertTrue(profile.languages.filter(code="cs").exists())
        self.assertTrue(profile.secondary_languages.filter(code="cs").exists())
        self.assertTrue(profile.watched.exists())

    def test_userdata_compat(self):
        """Test importing user data from pre 3.6 release."""
        User.objects.create_user("test-3.6", "test36@example.com", "x")
        Project.objects.create(name="test", slug="test")
        call_command("importuserdata", USERDATA_JSON)
        profile = Profile.objects.get(user__username="test-3.6")
        self.assertTrue(profile.languages.filter(code="cs").exists())
        self.assertTrue(profile.secondary_languages.filter(code="cs").exists())
        self.assertTrue(profile.watched.exists())
