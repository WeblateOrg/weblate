# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.checks.mdx import SafeMDXCheck
from weblate.checks.tests.test_checks import CheckTestCase


class SafeMDXCheckTest(CheckTestCase):
    check = SafeMDXCheck()

    def setUp(self) -> None:
        super().setUp()
        self.test_good_matching = (
            "Hello, {props.name.toUpperCase()}",
            "Ahoj, {props.name.toUpperCase()}",
            "safe-mdx",
        )

        self.test_failure_1 = (
            "Hello, {props.name.toUpperCase()}",
            "Ahoj, {props.unauthorized.access()}",
            "safe-mdx",
        )
        self.test_failure_2 = ("Test {Math.PI * 100}", "Test {Math.PI*100}", "safe-mdx")
        self.test_failure_3 = ("Hello, {props.name.toUpperCase()}", "Ahoj", "safe-mdx")
        self.test_ignore_check = (
            "Hello, {test}",
            "Ahoj, {ignore}",
            "safe-mdx,ignore-safe-mdx",
        )
