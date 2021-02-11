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

from weblate.checks.glossary import GlossaryCheck
from weblate.checks.models import Check
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_TRANSLATED


class GlossaryCheckTest(ViewTestCase):
    check = GlossaryCheck()

    def setUp(self):
        super().setUp()
        self.unit = self.get_unit()
        self.unit.extra_flags = "check-glossary"
        self.unit.translate(self.user, "Ahoj světe!\n", STATE_TRANSLATED)
        # Clear unit caches
        self.unit.check_cache = {}
        self.unit.glossary_terms = None
        self.glossary = self.project.glossaries[0].translation_set.get(
            language=self.unit.translation.language
        )

    def add_glossary(self, target, context=""):
        self.glossary.add_units(None, [(context, "hello", target)])

    def test_missing(self):
        self.assertFalse(
            self.check.check_target(
                self.unit.get_source_plurals(),
                self.unit.get_target_plurals(),
                self.unit,
            )
        )

    def test_good(self):
        self.add_glossary("ahoj")
        self.assertFalse(
            self.check.check_target(
                self.unit.get_source_plurals(),
                self.unit.get_target_plurals(),
                self.unit,
            )
        )

    def test_forbidden(self):
        self.add_glossary("ahoj")
        self.glossary.unit_set.all().update(extra_flags="forbidden")
        self.assertTrue(
            self.check.check_target(
                self.unit.get_source_plurals(),
                self.unit.get_target_plurals(),
                self.unit,
            )
        )

    def test_bad(self):
        self.add_glossary("nazdar")
        self.assertTrue(
            self.check.check_target(
                self.unit.get_source_plurals(),
                self.unit.get_target_plurals(),
                self.unit,
            )
        )

    def test_multi(self):
        self.add_glossary("nazdar")
        self.add_glossary("ahoj", "2")
        self.assertFalse(
            self.check.check_target(
                self.unit.get_source_plurals(),
                self.unit.get_target_plurals(),
                self.unit,
            )
        )

    def test_description(self):
        self.test_bad()
        check = Check(unit=self.unit)
        self.assertEqual(
            self.check.get_description(check),
            "Following terms are not translated according to glossary: hello",
        )
