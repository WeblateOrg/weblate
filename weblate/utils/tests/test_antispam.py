# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase, skipIf

import responses
from django.http import HttpRequest
from django.test.utils import override_settings

from weblate.utils.antispam import is_spam, report_spam

try:
    import akismet  # noqa: F401

    HAS_AKISMET = True
except ImportError:
    HAS_AKISMET = False


class SpamTest(TestCase):
    @override_settings(AKISMET_API_KEY=None)
    def test_disabled(self):
        self.assertFalse(is_spam("text", HttpRequest()))

    def mock_akismet(self, body, **kwargs):
        responses.add(
            responses.POST,
            "https://key.rest.akismet.com/1.1/comment-check",
            body=body,
            **kwargs,
        )
        responses.add(
            responses.POST,
            "https://key.rest.akismet.com/1.1/submit-spam",
            body=body,
            **kwargs,
        )
        responses.add(
            responses.POST, "https://rest.akismet.com/1.1/verify-key", body="valid"
        )

    @skipIf(not HAS_AKISMET, "akismet module not installed")
    @responses.activate
    @override_settings(AKISMET_API_KEY="key")
    def test_akismet_spam(self):
        self.mock_akismet("true")
        self.assertFalse(is_spam("text", HttpRequest()))

    @skipIf(not HAS_AKISMET, "akismet module not installed")
    @responses.activate
    @override_settings(AKISMET_API_KEY="key")
    def test_akismet_definite_spam(self):
        self.mock_akismet("true", headers={"X-Akismet-Pro-Tip": "discard"})
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
