# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest import TestCase

import responses
from django.core.exceptions import ImproperlyConfigured
from django.test.utils import override_settings

from weblate.utils.zammad import submit_zammad_ticket


class ZammadTest(TestCase):
    def mock_zammad(self) -> None:
        submit_url = "https://example.com/api/v1/form_submit"
        responses.add(
            responses.POST,
            "https://example.com/api/v1/form_config",
            json={"enabled": True, "endpoint": submit_url, "token": "token"},
        )
        responses.add(
            responses.POST, submit_url, json={"ticket": {"id": 123, "number": 4123}}
        )

    @override_settings(ZAMMAD_URL=None)
    @responses.activate
    def test_unconfigured(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            submit_zammad_ticket(title="title", body="body", name="name", email="mail")

    @override_settings(ZAMMAD_URL=None)
    @responses.activate
    def test_unconfigured_override(self) -> None:
        self.mock_zammad()
        self.assertEqual(
            submit_zammad_ticket(
                title="title",
                body="body",
                name="name",
                email="mail",
                zammad_url="https://example.com",
            ),
            ("https://example.com/#ticket/zoom/123", "4123"),
        )

    @override_settings(ZAMMAD_URL="https://example.com")
    @responses.activate
    def test_configured(self) -> None:
        self.mock_zammad()
        self.assertEqual(
            submit_zammad_ticket(title="title", body="body", name="name", email="mail"),
            ("https://example.com/#ticket/zoom/123", "4123"),
        )
