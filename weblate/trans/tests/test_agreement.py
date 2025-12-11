# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for contributor license agreement management."""

from weblate.trans.models import ContributorAgreement
from weblate.trans.tests.test_views import FixtureTestCase


class AgreementTest(FixtureTestCase):
    def test_basic(self) -> None:
        self.assertFalse(
            ContributorAgreement.objects.has_agreed(self.user, self.component)
        )
        ContributorAgreement.objects.create(self.user, self.component)
        self.assertTrue(
            ContributorAgreement.objects.has_agreed(self.user, self.component)
        )

    def test_perms(self) -> None:
        self.assertTrue(self.user.has_perm("unit.edit", self.component))
        self.component.agreement = "CLA"
        self.user.clear_cache()
        self.assertFalse(self.user.has_perm("unit.edit", self.component))
        ContributorAgreement.objects.create(self.user, self.component)
        self.user.clear_cache()
        self.assertTrue(self.user.has_perm("unit.edit", self.component))
