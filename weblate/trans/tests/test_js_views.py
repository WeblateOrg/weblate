# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for AJAX/JS views."""

from django.urls import reverse

from weblate.trans.tests.test_views import FixtureTestCase


class JSViewsTest(FixtureTestCase):
    """Testing of AJAX/JS views."""

    def test_get_unit_translations(self) -> None:
        unit = self.get_unit()
        response = self.client.get(
            reverse("js-unit-translations", kwargs={"unit_id": unit.id})
        )
        self.assertContains(response, 'href="/translate/')
