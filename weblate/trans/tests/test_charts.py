# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for charts and widgets."""

from django.urls import reverse

from weblate.trans.tests.test_views import FixtureTestCase


class ChartsTest(FixtureTestCase):
    """Testing of charts."""

    def test_activity_monthly(self) -> None:
        """Test of monthly activity charts."""
        response = self.client.get(reverse("monthly_activity_json"))
        self.assertEqual(len(response.json()), 52)
