# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for user handling."""

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from weblate.auth.models import Group, User
from weblate.trans.tests.utils import TempDirMixin, get_test_file


class CommandTest(TestCase, TempDirMixin):
    """Test for management commands."""

    def test_createadmin(self) -> None:
        call_command("createadmin")
        user = User.objects.get(username="admin")
        self.assertEqual(user.full_name, "Weblate Admin")
        self.assertFalse(user.check_password("admin"))

    def test_createadmin_password(self) -> None:
        call_command("createadmin", password="admin")
        user = User.objects.get(username="admin")
        self.assertEqual(user.full_name, "Weblate Admin")
        self.assertTrue(user.check_password("admin"))

    def test_createadmin_reuse_password(self) -> None:
        call_command("createadmin", password="admin")
        user = User.objects.get(username="admin")
        self.assertEqual(user.full_name, "Weblate Admin")
        self.assertTrue(user.check_password("admin"))
        # Ensure the password is not changed when not needed
        old = user.password
        call_command("createadmin", password="admin", update=True)
        user = User.objects.get(username="admin")
        self.assertEqual(old, user.password)

    def test_createadmin_username(self) -> None:
        call_command("createadmin", username="admin2")
        user = User.objects.get(username="admin2")
        self.assertEqual(user.full_name, "Weblate Admin")

    def test_createadmin_email(self) -> None:
        call_command("createadmin", email="noreply1@weblate.org")
        user = User.objects.get(username="admin")
        self.assertEqual(user.email, "noreply1@weblate.org")

    def test_createadmin_twice(self) -> None:
        call_command("createadmin")
        with self.assertRaises(CommandError):
            call_command("createadmin")

    def test_createadmin_update(self) -> None:
        call_command("createadmin", update=True)
        call_command("createadmin", update=True, password="123456")
        user = User.objects.get(username="admin")
        self.assertTrue(user.check_password("123456"))

    def test_createadmin_update_duplicate(self) -> None:
        email = "noreply+admin@weblate.org"
        User.objects.create(username="another", email=email)
        call_command("createadmin", update=True)
        with self.assertRaises(CommandError):
            call_command("createadmin", update=True, password="123456", email=email)
        user = User.objects.get(username="another")
        self.assertFalse(user.check_password("123456"))

    def test_createadmin_update_email(self) -> None:
        email = "noreply+admin@weblate.org"
        User.objects.create(username="another", email=email)
        call_command("createadmin", update=True, password="123456", email=email)
        user = User.objects.get(username="another")
        self.assertTrue(user.check_password("123456"))

    def test_importusers(self) -> None:
        # First import
        call_command("importusers", get_test_file("users.json"))

        # Test that second import does not change anything
        user = User.objects.get(username="weblate")
        user.full_name = "Weblate test user"
        user.save()
        call_command("importusers", get_test_file("users.json"))
        user2 = User.objects.get(username="weblate")
        self.assertEqual(user.full_name, user2.full_name)

    def test_importdjangousers(self) -> None:
        # First import
        call_command("importusers", get_test_file("users-django.json"))
        self.assertEqual(User.objects.count(), 2)

    def test_import_empty_users(self) -> None:
        """Test importing empty file."""
        call_command("importusers", get_test_file("users-empty.json"))
        # Only anonymous user
        self.assertEqual(User.objects.count(), 1)

    def test_import_invalid_users(self) -> None:
        """Test error handling in user import."""
        call_command("importusers", get_test_file("users-invalid.json"))
        # Only anonymous user
        self.assertEqual(User.objects.count(), 1)

    def test_setupgroups(self) -> None:
        call_command("setupgroups")
        group = Group.objects.get(name="Users")
        self.assertTrue(group.roles.filter(name="Power user").exists())
