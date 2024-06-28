# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from django.http import HttpRequest

from weblate.utils.views import get_page_limit


def fake_request(page, limit):
    request = HttpRequest()
    request.GET["page"] = page
    request.GET["limit"] = limit
    return request


class PageLimitTest(TestCase):
    def test_defaults(self) -> None:
        self.assertEqual((1, 42), get_page_limit(fake_request("x", "x"), 42))

    def test_negative(self) -> None:
        self.assertEqual((1, 10), get_page_limit(fake_request("-1", "-1"), 42))

    def test_valid(self) -> None:
        self.assertEqual((33, 66), get_page_limit(fake_request("33", "66"), 42))
