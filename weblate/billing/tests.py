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

from datetime import timedelta
import os.path

from django.test import TestCase
from django.test.utils import override_settings
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from six import StringIO

from weblate.auth.models import User
from weblate.billing.models import Plan, Billing, Invoice
from weblate.trans.models import Project


TEST_DATA = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'test-data'
)


class BillingTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='bill',
            password='kill',
            email='noreply@example.net'
        )
        self.plan = Plan.objects.create(name='test', limit_projects=1, price=1.0)
        self.billing = Billing.objects.create(plan=self.plan)
        self.invoice = Invoice.objects.create(
            billing=self.billing,
            start=timezone.now().date() - timedelta(days=2),
            end=timezone.now().date() + timedelta(days=2),
            payment=10,
            ref='00000',
        )
        self.projectnum = 0

    def add_project(self):
        name = 'test{0}'.format(self.projectnum)
        self.projectnum += 1
        project = Project.objects.create(
            name=name, slug=name, access_control=Project.ACCESS_PROTECTED
        )
        self.billing.projects.add(project)
        project.add_user(self.user, '@Billing')

    def test_view_billing(self):
        self.add_project()
        # Not authenticated
        response = self.client.get(reverse('billing'))
        self.assertEqual(302, response.status_code,)

        # Random user
        User.objects.create_user('foo', 'foo@example.org', 'bar')
        self.client.login(username='foo', password='bar')
        response = self.client.get(reverse('billing'))
        self.assertNotContains(response, 'Current plan')

        # Owner
        self.client.login(username='bill', password='kill')
        response = self.client.get(reverse('billing'))
        self.assertContains(response, 'Current plan')

        # Admin
        self.user.is_superuser = True
        self.user.save()
        response = self.client.get(reverse('billing'))
        self.assertContains(response, 'Current plan')

    def test_limit_projects(self):
        self.assertTrue(self.billing.in_limits)
        self.add_project()
        self.billing.refresh_from_db()
        self.assertTrue(self.billing.in_limits)
        self.add_project()
        self.billing.refresh_from_db()
        self.assertFalse(self.billing.in_limits)

    def test_commands(self):
        out = StringIO()
        call_command('billing_check', stdout=out)
        self.assertEqual(out.getvalue(), '')
        self.add_project()
        self.add_project()
        out = StringIO()
        call_command('billing_check', stdout=out)
        self.assertEqual(
            out.getvalue(),
            'Following billings are over limit:\n'
            ' * test0, test1 (test)\n'
        )
        out = StringIO()
        call_command('billing_check', '--valid', stdout=out)
        self.assertEqual(out.getvalue(), '')
        self.invoice.delete()
        out = StringIO()
        call_command('billing_check', stdout=out)
        self.assertEqual(
            out.getvalue(),
            'Following billings are over limit:\n'
            ' * test0, test1 (test)\n'
            'Following billings are past due date:\n'
            ' * test0, test1 (test)\n'
        )
        call_command('billing_check', '--notify', stdout=out)
        self.assertEqual(len(mail.outbox), 1)

    def test_invoice_validation(self):
        invoice = Invoice(
            billing=self.billing,
            start=self.invoice.start,
            end=self.invoice.end,
            payment=30
        )
        # Full overlap
        self.assertRaises(
            ValidationError,
            invoice.clean
        )

        # Start overlap
        invoice.start = self.invoice.end + timedelta(days=1)
        self.assertRaises(
            ValidationError,
            invoice.clean
        )

        # Zero interval
        invoice.end = self.invoice.end + timedelta(days=1)
        self.assertRaises(
            ValidationError,
            invoice.clean
        )

        # Valid after existing
        invoice.end = self.invoice.end + timedelta(days=2)
        invoice.clean()

        # End overlap
        invoice.start = self.invoice.start - timedelta(days=4)
        invoice.end = self.invoice.end
        self.assertRaises(
            ValidationError,
            invoice.clean
        )

        # Valid before existing
        invoice.end = self.invoice.start - timedelta(days=1)
        invoice.clean()

        # Validation of existing
        self.invoice.clean()

    @override_settings(INVOICE_PATH=TEST_DATA)
    def test_download(self):
        self.add_project()
        # Unauthenticated
        response = self.client.get(
            reverse('invoice-download', kwargs={'pk': self.invoice.pk})
        )
        self.assertEqual(302, response.status_code)
        # Not owner
        User.objects.create_user('foo', 'foo@example.org', 'bar')
        self.client.login(username='foo', password='bar')
        response = self.client.get(
            reverse('invoice-download', kwargs={'pk': self.invoice.pk})
        )
        self.assertEqual(403, response.status_code)
        # Owner
        self.client.login(username='bill', password='kill')
        response = self.client.get(
            reverse('invoice-download', kwargs={'pk': self.invoice.pk})
        )
        self.assertContains(response, 'PDF-INVOICE')
        # Invoice without file
        invoice = Invoice.objects.create(
            billing=self.billing,
            start=timezone.now().date() - timedelta(days=2),
            end=timezone.now().date() + timedelta(days=2),
            payment=10,
        )
        response = self.client.get(
            reverse('invoice-download', kwargs={'pk': invoice.pk})
        )
        self.assertEqual(404, response.status_code)
        # Invoice with non existing file
        invoice.ref = 'NON'
        invoice.save()
        response = self.client.get(
            reverse('invoice-download', kwargs={'pk': invoice.pk})
        )
        self.assertEqual(404, response.status_code)
