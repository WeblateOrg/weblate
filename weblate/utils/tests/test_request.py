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

from weblate.utils.request import get_ip_address, get_user_agent


class RequestTest(TestCase):
    def test_get_ip(self):
        request = HttpRequest()
        request.META["REMOTE_ADDR"] = "1.2.3.4"
        self.assertEqual(get_ip_address(request), "1.2.3.4")

    def test_agent(self):
        request = HttpRequest()
        request.META["HTTP_USER_AGENT"] = "agent"
        self.assertEqual(get_user_agent(request), "Other / Other / Other")

    def test_agent_long(self):
        request = HttpRequest()
        request.META["HTTP_USER_AGENT"] = "agent " * 200
        self.assertLess(len(get_user_agent(request)), 200)
