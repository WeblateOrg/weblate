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

from unittest import TestCase, skipIf

import responses
from django.http import HttpRequest
from django.test.utils import override_settings

from weblate.utils.antispam import is_spam, report_spam

try:
    # pylint: disable=unused-import
    import akismet  # noqa: F401

    HAS_AKISMET = True
except ImportError:
    HAS_AKISMET = False


class SpamTest(TestCase):
    @override_settings(AKISMET_API_KEY=None)
    def test_disabled(self):
        self.assertFalse(is_spam("text", HttpRequest()))

    def mock_akismet(self, body):
        responses.add(
            responses.POST, "https://key.rest.akismet.com/1.1/comment-check", body=body
        )
        responses.add(
            responses.POST, "https://key.rest.akismet.com/1.1/submit-spam", body=body
        )
        responses.add(
            responses.POST, "https://rest.akismet.com/1.1/verify-key", body="valid"
        )

    @skipIf(not HAS_AKISMET, "akismet module not installed")
    @responses.activate
    @override_settings(AKISMET_API_KEY="key")
    def test_akismet_spam(self):
        self.mock_akismet("true")
        self.assertTrue(is_spam("text", HttpRequest()))

    @skipIf(not HAS_AKISMET, "akismet module not installed")
    @responses.activate
    @override_settings(AKISMET_API_KEY="key")
    def test_akismet_nospam(self):
        self.mock_akismet("false")
        self.assertFalse(is_spam("text", HttpRequest()))

    @skipIf(not HAS_AKISMET, "akismet module not installed")
    @responses.activate
    @override_settings(AKISMET_API_KEY="key")
    def test_akismet_submit_spam(self):
        self.mock_akismet("Thanks for making the web a better place.")
        self.assertIsNone(report_spam("1.2.3.4", "Agent", "text"))

    @skipIf(not HAS_AKISMET, "akismet module not installed")
    @responses.activate
    @override_settings(AKISMET_API_KEY="key")
    def test_akismet_submit_spam_error(self):
        self.mock_akismet("false")
        self.assertIsNone(report_spam("1.2.3.4", "Agent", "text"))
