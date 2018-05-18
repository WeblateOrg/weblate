# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

"""Test for contributor agreement management."""

from weblate.trans.models import ContributorAgreement
from weblate.trans.tests.test_views import FixtureTestCase


class AgreementTest(FixtureTestCase):
    def test_basic(self):
        self.assertFalse(
            ContributorAgreement.objects.has_agreed(
                self.user,
                self.component,
            )
        )
        ContributorAgreement.objects.create(self.user, self.component)
        self.assertTrue(
            ContributorAgreement.objects.has_agreed(
                self.user,
                self.component,
            )
        )

    def test_perms(self):
        self.assertTrue(
            self.user.has_perm('unit.edit', self.component)
        )
        self.component.agreement = 'CLA'
        self.user.clear_cache()
        self.assertFalse(
            self.user.has_perm('unit.edit', self.component)
        )
        ContributorAgreement.objects.create(self.user, self.component)
        self.user.clear_cache()
        self.assertTrue(
            self.user.has_perm('unit.edit', self.component)
        )
