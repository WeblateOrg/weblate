# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.test import SimpleTestCase
from django.test.utils import override_settings

from weblate.utils.decorators import engage_login_not_required


class DecoratorTestCase(SimpleTestCase):
    def test_engage_login_not_required(self):
        with override_settings(REQUIRE_LOGIN=True, PUBLIC_ENGAGE=True):
            self.assertFalse(engage_login_not_required(lambda: None).login_required)
        with override_settings(REQUIRE_LOGIN=True, PUBLIC_ENGAGE=False):
            self.assertFalse(
                hasattr(engage_login_not_required(lambda: None), "login_required")
            )
        with override_settings(REQUIRE_LOGIN=False, PUBLIC_ENGAGE=False):
            self.assertFalse(
                hasattr(engage_login_not_required(lambda: None), "login_required")
            )
        with override_settings(REQUIRE_LOGIN=False, PUBLIC_ENGAGE=True):
            self.assertFalse(
                hasattr(engage_login_not_required(lambda: None), "login_required")
            )
