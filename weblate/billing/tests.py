# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from StringIO import StringIO

from django.test import TestCase
from django.contrib.auth.models import User
from django.core.management import call_command

from weblate.billing.models import Plan, Billing
from weblate.trans.models import Project


class BillingTest(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='bill')
        self.plan = Plan.objects.create(name='test', limit_projects=1, price=0)
        self.billing = Billing.objects.create(user=self.user, plan=self.plan)
        self.projectnum = 0

    def add_project(self):
        name = 'test{0}'.format(self.projectnum)
        self.projectnum += 1
        self.billing.projects.add(
            Project.objects.create(name=name, slug=name)
        )

    def test_limit_projects(self):
        self.assertTrue(self.billing.in_limits())
        self.add_project()
        self.assertTrue(self.billing.in_limits())
        self.add_project()
        self.assertFalse(self.billing.in_limits())

    def test_commands(self):
        out = StringIO()
        call_command('billing_check', stdout=out)
        self.assertEqual(out.getvalue(), '')
        self.add_project()
        self.add_project()
        call_command('billing_check', stdout=out)
        self.assertEqual(
            out.getvalue(),
            'Following billings are over limit:\n * bill (test)\n'
        )
