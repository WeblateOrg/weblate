# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from django.http import HttpRequest

from weblate.trans.debug import WeblateExceptionReporterFilter


class ReportFilterTest(TestCase):
    def test_report_none(self) -> None:
        reporter = WeblateExceptionReporterFilter()
        result = reporter.get_post_parameters(None)
        self.assertEqual(result, {})

    def test_report_request(self) -> None:
        reporter = WeblateExceptionReporterFilter()
        request = HttpRequest()
        reporter.get_post_parameters(request)
        self.assertIn("WEBLATE_VERSION:Weblate", request.META)

    def test_report_language(self) -> None:
        reporter = WeblateExceptionReporterFilter()
        request = HttpRequest()
        request.session = {"django_language": "testlang"}
        reporter.get_post_parameters(request)
        self.assertIn("WEBLATE_LANGUAGE", request.META)
