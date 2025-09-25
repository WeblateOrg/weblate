# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from django.http import HttpRequest

from weblate.utils.antispam import is_spam, report_spam


class SpamTest(TestCase):
    def test_is_spam_always_false(self) -> None:
        """Test that is_spam always returns False after Akismet removal."""
        self.assertFalse(is_spam(HttpRequest(), "text"))
        self.assertFalse(is_spam(HttpRequest(), ["text"]))
        self.assertFalse(is_spam(HttpRequest(), ""))
        self.assertFalse(is_spam(HttpRequest(), [""]))

    def test_report_spam_noop(self) -> None:
        """Test that report_spam is a no-op after Akismet removal."""
        # Should not raise any exceptions
        report_spam("text", "1.2.3.4", "Agent")
