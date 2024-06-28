# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from django.http.request import HttpRequest

from weblate.utils.request import get_ip_address, get_user_agent


class RequestTest(TestCase):
    def test_get_ip(self) -> None:
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "1.2.3.4"
        self.assertEqual(get_ip_address(request), "1.2.3.4")

    def test_agent(self) -> None:
        request = HttpRequest()
        request.META["HTTP_USER_AGENT"] = "agent"
        self.assertEqual(get_user_agent(request), "Other / Other / Other")

    def test_agent_long(self) -> None:
        request = HttpRequest()
        request.META["HTTP_USER_AGENT"] = "agent " * 200
        self.assertLess(len(get_user_agent(request)), 200)
