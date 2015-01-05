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

from unittest import TestCase
from django.http import HttpRequest
from weblate.trans.debug import WeblateExceptionReporterFilter


class ReportFilterTest(TestCase):
    def test_report_none(self):
        reporter = WeblateExceptionReporterFilter()
        result = reporter.get_request_repr(None)
        self.assertEqual(
            'None',
            result
        )

    def test_report_request(self):
        reporter = WeblateExceptionReporterFilter()
        result = reporter.get_request_repr(HttpRequest())
        self.assertIn(
            'HttpRequest',
            result
        )

    def test_report_language(self):
        reporter = WeblateExceptionReporterFilter()
        request = HttpRequest()
        request.session = {'django_language': 'testlang'}
        result = reporter.get_request_repr(request)
        self.assertIn(
            'testlang',
            result
        )
