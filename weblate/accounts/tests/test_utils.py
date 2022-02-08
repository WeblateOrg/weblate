#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

"""Tests for various helper utilities."""


from django.test import TestCase

from weblate.accounts.pipeline import slugify_username
from weblate.accounts.tasks import cleanup_auditlog, cleanup_social_auth


class PipelineTest(TestCase):
    def test_slugify(self):
        self.assertEqual(slugify_username("zkouska"), "zkouska")
        self.assertEqual(slugify_username("Zkouska"), "Zkouska")
        self.assertEqual(slugify_username("zkouška"), "zkouska")
        self.assertEqual(slugify_username(" zkouska "), "zkouska")
        self.assertEqual(slugify_username("ahoj - ahoj"), "ahoj-ahoj")
        self.assertEqual(slugify_username("..test"), "test")


class TasksTest(TestCase):
    def test_cleanup_social_auth(self):
        cleanup_social_auth()

    def test_cleanup_auditlog(self):
        cleanup_auditlog()
