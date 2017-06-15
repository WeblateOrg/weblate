# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from time import sleep
from unittest import TestCase

from django.test.utils import override_settings

from weblate.accounts.ratelimit import (
    reset_rate_limit, check_rate_limit, get_ip_address,
)


META = {
    'REMOTE_ADDR': '1.2.3.4',
    'HTTP_X_FORWARDED_FOR': '7.8.9.0',
}


class FakeRequest(object):
    """Fake Request mock for testing rate limiting."""
    def __init__(self):
        self.META = META


class RateLimitTest(TestCase):
    def setUp(self):
        # Ensure no rate limits are there
        for address in META.values():
            reset_rate_limit(address=address)

    def test_basic(self):
        self.assertTrue(
            check_rate_limit(FakeRequest())
        )

    @override_settings(AUTH_MAX_ATTEMPTS=5, AUTH_CHECK_WINDOW=60)
    def test_limit(self):
        request = FakeRequest()
        for dummy in range(5):
            self.assertTrue(
                check_rate_limit(request)
            )

        self.assertFalse(
            check_rate_limit(request)
        )

    @override_settings(
        AUTH_MAX_ATTEMPTS=1,
        AUTH_CHECK_WINDOW=2,
        AUTH_LOCKOUT_TIME=1
    )
    def test_window(self):
        request = FakeRequest()
        self.assertTrue(
            check_rate_limit(request)
        )
        sleep(1)
        self.assertFalse(
            check_rate_limit(request)
        )
        sleep(1)
        self.assertTrue(
            check_rate_limit(request)
        )

    @override_settings(
        AUTH_MAX_ATTEMPTS=1,
        AUTH_CHECK_WINDOW=2,
        AUTH_LOCKOUT_TIME=100
    )
    def test_lockout(self):
        request = FakeRequest()
        self.assertTrue(
            check_rate_limit(request)
        )
        sleep(1)
        self.assertFalse(
            check_rate_limit(request)
        )
        sleep(1)
        self.assertFalse(
            check_rate_limit(request)
        )

    @override_settings(
        IP_BEHIND_REVERSE_PROXY=False,
        IP_PROXY_HEADER='HTTP_X_FORWARDED_FOR',
        IP_PROXY_OFFSET=0
    )
    def test_get_ip(self):
        request = FakeRequest()
        self.assertEqual(
            get_ip_address(request),
            '1.2.3.4'
        )

    @override_settings(
        IP_BEHIND_REVERSE_PROXY=True,
        IP_PROXY_HEADER='HTTP_X_FORWARDED_FOR',
        IP_PROXY_OFFSET=0
    )
    def test_get_ip_proxy(self):
        request = FakeRequest()
        self.assertEqual(
            get_ip_address(request),
            '7.8.9.0'
        )
