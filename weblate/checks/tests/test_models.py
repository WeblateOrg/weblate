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
from weblate.checks.tasks import batch_update_checks
from weblate.trans.models import Unit
from weblate.trans.tasks import auto_translate
from weblate.trans.tests.test_views import FixtureTestCase, ViewTestCase


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


class BatchUpdateTest(ViewTestCase):
    """Test for complex manipulating translation."""

    def setUp(self):
        super().setUp()
        self.translation = self.get_translation()

    def do_base(self):
        # Single unit should have no consistency check
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, set())

        # Add linked project
        other = self.create_link_existing()

        # Now the inconsistent check should be there
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, {"inconsistent"})
        return other

    def test_autotranslate(self):
        other = self.do_base()
        translation = other.translation_set.get(language_code="cs")
        auto_translate(
            None,
            translation.pk,
            "translate",
            "todo",
            "others",
            self.component.pk,
            [],
            99,
            translation=translation,
        )
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, set())

    def test_noop(self):
        other = self.do_base()
        # The batch update should not remove it
        batch_update_checks(self.component.id, ["inconsistent"])
        batch_update_checks(other.id, ["inconsistent"])
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, {"inconsistent"})

    def test_toggle(self):
        other = self.do_base()
        one_unit = self.get_unit()
        other_unit = Unit.objects.get(
            translation__language_code=one_unit.translation.language_code,
            translation__component=other,
            id_hash=one_unit.id_hash,
        )
        translated = one_unit.target

        combinations = (
            (translated, "", {"inconsistent"}),
            ("", translated, {"inconsistent"}),
            ("", "", set()),
            (translated, translated, set()),
            ("", translated, {"inconsistent"}),
        )
        for update_one, update_other, expected in combinations:
            Unit.objects.filter(pk=one_unit.pk).update(target=update_one)
            Unit.objects.filter(pk=other_unit.pk).update(target=update_other)

            batch_update_checks(self.component.id, ["inconsistent"])
            unit = self.get_unit()
            self.assertEqual(unit.all_checks_names, expected)

        for update_one, update_other, expected in combinations:
            Unit.objects.filter(pk=one_unit.pk).update(target=update_one)
            Unit.objects.filter(pk=other_unit.pk).update(target=update_other)

            batch_update_checks(other.id, ["inconsistent"])
            unit = self.get_unit()
            self.assertEqual(unit.all_checks_names, expected)
