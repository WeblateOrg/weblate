# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for notitifications."""

from __future__ import annotations

from django.test import SimpleTestCase

from weblate.accounts.models import AuditLog


class AuditLogTestCase(SimpleTestCase):
    def test_address_ipv4(self):
        audit = AuditLog(address="127.0.0.1")
        self.assertEqual(audit.shortened_address, "127.0.0.0")

    def test_address_ipv6_local(self):
        audit = AuditLog(address="fe80::54c2:1234:5678:90ab")
        self.assertEqual(audit.shortened_address, "fe80::")

    def test_address_ipv6_weblate(self):
        audit = AuditLog(address="2a01:4f8:c0c:a84b::1")
        self.assertEqual(audit.shortened_address, "2a01:4f8:c0c::")

    def test_address_blank(self):
        audit = AuditLog()
        self.assertEqual(audit.shortened_address, "")
