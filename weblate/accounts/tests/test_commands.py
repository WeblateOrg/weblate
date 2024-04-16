# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

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

    def test_userdata(self) -> None:
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

    def test_userdata_compat(self) -> None:
        """Test importing user data from pre 3.6 release."""
        User.objects.create_user("test-3.6", "test36@example.com", "x")
        Project.objects.create(name="test", slug="test")
        call_command("importuserdata", USERDATA_JSON)
        profile = Profile.objects.get(user__username="test-3.6")
        self.assertTrue(profile.languages.filter(code="cs").exists())
        self.assertTrue(profile.secondary_languages.filter(code="cs").exists())
        self.assertTrue(profile.watched.exists())
