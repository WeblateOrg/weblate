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

from time import sleep

from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage import default_storage
from django.http.request import HttpRequest
from django.test.utils import override_settings
from django.test import SimpleTestCase

from weblate.utils.ratelimit import (
    reset_rate_limit, check_rate_limit, session_ratelimit_post,
)


class RateLimitTest(SimpleTestCase):
    def get_request(self):
        request = HttpRequest()
        request.META['REMOTE_ADDR'] = '1.2.3.4'
        request.method = 'POST'
        request.session = {}
        request._messages = default_storage(request)
        request.user = AnonymousUser()
        return request

    def setUp(self):
        # Ensure no rate limits are there
        reset_rate_limit('test', address='1.2.3.4')

    def test_basic(self):
        self.assertTrue(
            check_rate_limit('test', self.get_request())
        )

    @override_settings(
        RATELIMIT_ATTEMPTS=5,
        RATELIMIT_WINDOW=60,
    )
    def test_limit(self):
        request = self.get_request()
        for dummy in range(5):
            self.assertTrue(
                check_rate_limit('test', request)
            )

        self.assertFalse(
            check_rate_limit('test', request)
        )

    @override_settings(
        RATELIMIT_ATTEMPTS=1,
        RATELIMIT_WINDOW=2,
        RATELIMIT_LOCKOUT=1,
    )
    def test_window(self):
        request = self.get_request()
        self.assertTrue(
            check_rate_limit('test', request)
        )
        sleep(1)
        self.assertFalse(
            check_rate_limit('test', request)
        )
        sleep(1)
        self.assertTrue(
            check_rate_limit('test', request)
        )

    @override_settings(
        RATELIMIT_ATTEMPTS=1,
        RATELIMIT_WINDOW=2,
        RATELIMIT_LOCKOUT=100,
    )
    def test_lockout(self):
        request = self.get_request()
        self.assertTrue(
            check_rate_limit('test', request)
        )
        sleep(1)
        self.assertFalse(
            check_rate_limit('test', request)
        )
        sleep(1)
        self.assertFalse(
            check_rate_limit('test', request)
        )

    @override_settings(
        RATELIMIT_ATTEMPTS=1,
        RATELIMIT_WINDOW=1,
    )
    def test_session(self):
        request = self.get_request()

        limiter = session_ratelimit_post('test')(lambda request: 'RESPONSE')

        self.assertEqual(limiter(request), 'RESPONSE')
        self.assertEqual(limiter(request).url, '/accounts/login/')
        self.assertEqual(limiter(request).url, '/accounts/login/')
        sleep(1)
        self.assertEqual(limiter(request), 'RESPONSE')
