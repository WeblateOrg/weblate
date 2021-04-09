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
from weblate.checks.models import Check
from weblate.checks.tests.test_checks import CheckTestCase, MockUnit
from weblate.trans.models import Unit


class DuplicateCheckTest(CheckTestCase):

    check = DuplicateCheck()

    def _run_check(self, target, source="", lang="cs"):
        return self.check.check_single(source, target, MockUnit(code=lang, note=""))

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

    def test_check_duplicated_numbers(self):
        self.assertFalse(self._run_check("I have 222 222 lemons"))

    def test_check_duplicated_letter(self):
        self.assertFalse(self._run_check("I have A A A"))

    def test_check_duplicated_source(self):
        self.assertFalse(
            self._run_check("begin begin end end", source="begin begin end end")
        )

    def test_check_duplicated_language_ignore(self):
        self.assertFalse(self._run_check("Si vous vous interrogez", lang="fr"))

    def test_description(self):
        unit = Unit(source="string", target="I have two two lemons lemons")
        check = Check(unit=unit)
        self.assertEqual(
            self.check.get_description(check),
            "Text contains the same word twice in a row: lemons, two",
        )

    def test_check_duplicated_language_cleanup(self):
        self.assertFalse(self._run_check("Cancel·la la baixada", lang="ca"))

    def test_separator(self):
        self.assertFalse(self._run_check("plug-in in"))
