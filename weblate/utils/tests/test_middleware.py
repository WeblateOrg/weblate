#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from unittest import TestCase

from django.http.request import HttpRequest
from django.test.utils import override_settings

from weblate.middleware import ProxyMiddleware


class ProxyTest(TestCase):
    def get_response(self, request):
        self.assertEqual(request.META["REMOTE_ADDR"], "1.2.3.4")
        return "response"

    @override_settings(
        IP_BEHIND_REVERSE_PROXY=False,
        IP_PROXY_HEADER="HTTP_X_FORWARDED_FOR",
        IP_PROXY_OFFSET=0,
    )
    def test_direct(self):
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "1.2.3.4"
        middleware = ProxyMiddleware(self.get_response)
        self.assertEqual(middleware(request), "response")

    @override_settings(
        IP_BEHIND_REVERSE_PROXY=True,
        IP_PROXY_HEADER="HTTP_X_FORWARDED_FOR",
        IP_PROXY_OFFSET=0,
    )
    def test_proxy(self):
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "7.8.9.0"
        request.META["HTTP_X_FORWARDED_FOR"] = "1.2.3.4"
        middleware = ProxyMiddleware(self.get_response)
        self.assertEqual(middleware(request), "response")

    @override_settings(
        IP_BEHIND_REVERSE_PROXY=True,
        IP_PROXY_HEADER="HTTP_X_FORWARDED_FOR",
        IP_PROXY_OFFSET=1,
    )
    def test_proxy_second(self):
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "7.8.9.0"
        request.META["HTTP_X_FORWARDED_FOR"] = "2.3.4.5, 1.2.3.4"
        middleware = ProxyMiddleware(self.get_response)
        self.assertEqual(middleware(request), "response")

    @override_settings(
        IP_BEHIND_REVERSE_PROXY=True,
        IP_PROXY_HEADER="HTTP_X_FORWARDED_FOR",
        IP_PROXY_OFFSET=0,
    )
    def test_proxy_invalid(self):
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "1.2.3.4"
        request.META["HTTP_X_FORWARDED_FOR"] = "2.3.4"
        middleware = ProxyMiddleware(self.get_response)
        self.assertEqual(middleware(request), "response")
