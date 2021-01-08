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

"""Tests for review workflow."""

from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_APPROVED


class ReviewTest(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.project.translation_review = True
        self.project.save()

    def approve(self):
        unit = self.get_unit()
        unit.target = "Ahoj svete!\n"
        unit.state = STATE_APPROVED
        unit.save()

    def check_result(self, fail):
        unit = self.get_unit()
        if fail:
            self.assertTrue(unit.approved)
            self.assertEqual(unit.target, "Ahoj svete!\n")
        else:
            self.assertFalse(unit.approved)
            self.assertEqual(unit.target, "Nazdar svete!\n")

    def test_approve(self):
        self.make_manager()
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", review=str(STATE_APPROVED))
        unit = self.get_unit()
        self.assertTrue(unit.approved)

    def test_edit_approved(self, fail=True):
        self.approve()
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.check_result(fail)

    def test_edit_reviewer(self):
        self.make_manager()
        self.test_edit_approved(False)

    def test_suggest(self, fail=True):
        self.approve()
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", suggest="yes")

        # Get ids of created suggestions
        suggestion = self.get_unit().suggestions[0].pk

        # Accept one of suggestions
        self.edit_unit("Hello, world!\n", "", accept_edit=suggestion)
        self.check_result(fail)

    def test_suggest_reviewr(self):
        self.make_manager()
        self.test_suggest(False)
