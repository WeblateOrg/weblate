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
            "",
        )

        self.test_failure_1 = (
            "Hello, {props.name.toUpperCase()}",
            "Ahoj, {props.unauthorized.access()}",
            "",
        )
        self.test_failure_2 = ("Test {Math.PI * 100}", "Test {Math.PI*100}", "")
        self.test_failure_3 = ("Hello, {props.name.toUpperCase()}", "Ahoj", "")
        self.test_ignore = ("Hello, {test}", "Ahoj, {ignore}", "ignore-safe-mdx")
