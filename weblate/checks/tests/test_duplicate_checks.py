#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

"""Tests for duplicate checks."""


from weblate.checks.duplicate import DuplicateCheck
from weblate.checks.tests.test_checks import CheckTestCase, MockUnit


class DuplicateCheckTest(CheckTestCase):

    check = DuplicateCheck()

    _MOCK_UNIT = MockUnit(code="cs", note="")

    def _run_check(self, target):
        return self.check.check_single("", target, self._MOCK_UNIT)

    def test_no_duplicated_token(self):
        self.assertFalse(self._run_check("I have two lemons"))

    def test_check_respects_boundaries_suffix(self):
        """'lemon lemon' is a false duplicate."""
        self.assertFalse(self._run_check("I have two lemon lemons"))

    def test_check_respects_boundaries_prefix(self):
        """'melon on' is a false duplicate."""
        self.assertFalse(self._run_check("I have a melon on my back"))

    def test_check_single_duplicated_token(self):
        self.assertTrue(self._run_check("I have two two lemons"))

    def test_check_multiple_duplicated_tokens(self):
        self.assertTrue(self._run_check("I have two two lemons lemons"))
