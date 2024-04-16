# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for review workflow."""

from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_APPROVED


class ReviewTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project.translation_review = True
        self.project.save()

    def approve(self) -> None:
        unit = self.get_unit()
        unit.target = "Ahoj svete!\n"
        unit.state = STATE_APPROVED
        unit.save()

    def check_result(self, fail) -> None:
        unit = self.get_unit()
        if fail:
            self.assertTrue(unit.approved)
            self.assertEqual(unit.target, "Ahoj svete!\n")
        else:
            self.assertFalse(unit.approved)
            self.assertEqual(unit.target, "Nazdar svete!\n")

    def test_approve(self) -> None:
        self.make_manager()
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", review=str(STATE_APPROVED))
        unit = self.get_unit()
        self.assertTrue(unit.approved)

    def test_edit_approved(self, fail=True) -> None:
        self.approve()
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        self.check_result(fail)

    def test_edit_reviewer(self) -> None:
        self.make_manager()
        self.test_edit_approved(False)

    def test_suggest(self, fail=True) -> None:
        self.approve()
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n", suggest="yes")

        # Get ids of created suggestions
        suggestion = self.get_unit().suggestions[0].pk

        # Accept one of suggestions
        self.edit_unit("Hello, world!\n", "", accept_edit=suggestion)
        self.check_result(fail)

    def test_suggest_reviewr(self) -> None:
        self.make_manager()
        self.test_suggest(False)
