# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from django.test import SimpleTestCase

from weblate.utils.pii import mask_email


class PIITestCase(SimpleTestCase):
    def test_mask_email(self) -> None:
        self.assertEqual(mask_email("michal@cihar.com"), "m****l@*****.**m")
        self.assertEqual(mask_email("mic@localhost"), "***@********t")
        self.assertEqual(mask_email("michal@cz"), "m****l@*z")
