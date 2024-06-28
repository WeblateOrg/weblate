# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import TestCase

from weblate.auth.models import AutoGroup, Group, User


class AutoGroupTest(TestCase):
    @staticmethod
    def create_user():
        return User.objects.create_user("test1", "noreply1@weblate.org", "pass")

    def test_default(self) -> None:
        user = self.create_user()
        self.assertEqual(user.groups.count(), 2)

    def test_none(self) -> None:
        AutoGroup.objects.all().delete()
        user = self.create_user()
        self.assertEqual(user.groups.count(), 0)

    def test_matching(self) -> None:
        AutoGroup.objects.create(
            match="^.*@weblate.org", group=Group.objects.get(name="Guests")
        )
        user = self.create_user()
        self.assertEqual(user.groups.count(), 3)

    def test_nonmatching(self) -> None:
        AutoGroup.objects.create(
            match="^.*@example.net", group=Group.objects.get(name="Guests")
        )
        user = self.create_user()
        self.assertEqual(user.groups.count(), 2)
