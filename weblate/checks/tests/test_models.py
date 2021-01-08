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

"""Tests for unitdata models."""

from django.urls import reverse

from weblate.checks.models import Check
from weblate.trans.tests.test_views import FixtureTestCase


class CheckModelTestCase(FixtureTestCase):
    def create_check(self, name):
        return Check.objects.create(unit=self.get_unit(), check=name)

    def test_check(self):
        check = self.create_check("same")
        self.assertEqual(
            str(check.get_description()), "Source and translation are identical"
        )
        self.assertTrue(check.get_doc_url().endswith("user/checks.html#check-same"))
        self.assertEqual(str(check), "Unchanged translation")

    def test_check_nonexisting(self):
        check = self.create_check("-invalid-")
        self.assertEqual(check.get_description(), "-invalid-")
        self.assertEqual(check.get_doc_url(), "")

    def test_check_render(self):
        unit = self.get_unit()
        unit.source_unit.extra_flags = "max-size:1:1"
        unit.source_unit.save()
        check = self.create_check("max-size")
        url = reverse(
            "render-check", kwargs={"check_id": check.check, "unit_id": unit.id}
        )
        self.assertEqual(
            str(check.get_description()),
            '<a href="{0}?pos=0" class="thumbnail">'
            '<img class="img-responsive" src="{0}?pos=0" /></a>'.format(url),
        )
        self.assert_png(self.client.get(url))
