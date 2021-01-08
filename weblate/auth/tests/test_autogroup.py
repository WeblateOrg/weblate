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

from django.test import TestCase

from weblate.auth.models import AutoGroup, Group, User


class AutoGroupTest(TestCase):
    @staticmethod
    def create_user():
        return User.objects.create_user("test1", "noreply1@weblate.org", "pass")

    def test_default(self):
        user = self.create_user()
        self.assertEqual(user.groups.count(), 2)

    def test_none(self):
        AutoGroup.objects.all().delete()
        user = self.create_user()
        self.assertEqual(user.groups.count(), 0)

    def test_matching(self):
        AutoGroup.objects.create(
            match="^.*@weblate.org", group=Group.objects.get(name="Guests")
        )
        user = self.create_user()
        self.assertEqual(user.groups.count(), 3)

    def test_nonmatching(self):
        AutoGroup.objects.create(
            match="^.*@example.net", group=Group.objects.get(name="Guests")
        )
        user = self.create_user()
        self.assertEqual(user.groups.count(), 2)
