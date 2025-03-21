# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for unitdata models."""

from django.test import SimpleTestCase
from django.urls import reverse
from django.utils.html import format_html

from weblate.checks.models import CHECKS, Check
from weblate.checks.tasks import batch_update_checks
from weblate.trans.models import Unit
from weblate.trans.tasks import auto_translate
from weblate.trans.tests.test_views import FixtureTestCase, ViewTestCase


class CheckLintTestCase(SimpleTestCase):
    def test_check_id(self) -> None:
        for check in CHECKS.values():
            self.assertRegex(check.check_id, r"^[a-z][a-z0-9_-]*[a-z]$")
            self.assertTrue(
                check.description.endswith("."),
                f"{check.__class__.__name__} description does not have a stop: {check.description}",
            )


class CheckModelTestCase(FixtureTestCase):
    def create_check(self, name):
        return Check.objects.create(unit=self.get_unit(), name=name)

    def test_check(self) -> None:
        check = self.create_check("same")
        self.assertEqual(
            str(check.get_description()), "Source and translation are identical."
        )
        self.assertTrue(check.get_doc_url().endswith("user/checks.html#check-same"))
        self.assertEqual(str(check), "Unchanged translation")

    def test_check_nonexisting(self) -> None:
        check = self.create_check("-invalid-")
        self.assertEqual(check.get_description(), "-invalid-")
        self.assertEqual(check.get_doc_url(), "")

    def test_check_render(self) -> None:
        unit = self.get_unit()
        unit.source_unit.extra_flags = "max-size:1:1"
        unit.source_unit.save()
        check = self.create_check("max-size")
        url = reverse(
            "render-check", kwargs={"check_id": check.name, "unit_id": unit.id}
        )
        self.assertHTMLEqual(
            check.get_description(),
            format_html(
                '<a href="{0}?pos={1}" class="thumbnail img-check">'
                '<img class="img-responsive" src="{0}?pos={1}" /></a>',
                url,
                0,
            ),
        )
        self.assert_png(self.client.get(url))


class BatchUpdateTest(ViewTestCase):
    """Test for complex manipulating translation."""

    def setUp(self) -> None:
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

    def test_autotranslate(self) -> None:
        other = self.do_base()
        translation = other.translation_set.get(language_code="cs")
        auto_translate(
            user_id=None,
            translation_id=translation.pk,
            mode="translate",
            filter_type="todo",
            auto_source="others",
            component=self.component.pk,
            engines=[],
            threshold=99,
        )
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, set())

    def test_noop(self) -> None:
        other = self.do_base()
        # The batch update should not remove it
        batch_update_checks(self.component.id, ["inconsistent"])
        batch_update_checks(other.id, ["inconsistent"])
        unit = self.get_unit()
        self.assertEqual(unit.all_checks_names, {"inconsistent"})

    def test_toggle(self) -> None:
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
