# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from weblate.utils.db import re_escape


class DbTest(TestCase):
    def test_re_escape(self):
        self.assertEqual(re_escape("[a-z]"), "\\[a\\-z\\]")
        self.assertEqual(re_escape("a{1,4}"), "a\\{1,4\\}")
