# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock, patch

import httpx2
from django.core.exceptions import ImproperlyConfigured
from django.test.utils import override_settings

from weblate.utils.tests import http_mock
from weblate.utils.zammad import ZammadError, submit_zammad_ticket

ZAMMAD_URL = "https://example.com"
CONFIG_URL = f"{ZAMMAD_URL}/api/v1/form_config"
SUBMIT_URL = f"{ZAMMAD_URL}/api/v1/form_submit"
TICKET_DATA = {
    "title": "title",
    "body": "body",
    "name": "name",
    "email": "mail",
}


class ZammadTest(TestCase):
    def assert_zammad_failure(self) -> tuple[Mock, ZammadError]:
        with (
            patch("weblate.utils.zammad.report_error") as report_error,
            self.assertRaisesRegex(
                ZammadError, "Customer care is currently unavailable"
            ) as raised,
        ):
            submit_zammad_ticket(**TICKET_DATA)

        report_error.assert_called_once()
        return report_error, raised.exception

    def mock_zammad(self) -> None:
        http_mock.register(
            "POST",
            CONFIG_URL,
            json={"enabled": True, "endpoint": SUBMIT_URL, "token": "token"},
        )
        http_mock.register(
            "POST", SUBMIT_URL, json={"ticket": {"id": 123, "number": 4123}}
        )

    @override_settings(ZAMMAD_URL=None)
    @http_mock.activate
    def test_unconfigured(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            submit_zammad_ticket(**TICKET_DATA)

    @override_settings(ZAMMAD_URL=None)
    @http_mock.activate
    def test_unconfigured_override(self) -> None:
        self.mock_zammad()
        self.assertEqual(
            submit_zammad_ticket(
                **TICKET_DATA,
                zammad_url=ZAMMAD_URL,
            ),
            (f"{ZAMMAD_URL}/#ticket/zoom/123", "4123"),
        )

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_configured(self) -> None:
        self.mock_zammad()
        self.assertEqual(
            submit_zammad_ticket(**TICKET_DATA),
            (f"{ZAMMAD_URL}/#ticket/zoom/123", "4123"),
        )

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_invalid_json_encoding(self) -> None:
        http_mock.register(
            "POST",
            CONFIG_URL,
            content=b"\xff",
            headers={"Content-Type": "application/json"},
        )

        self.assert_zammad_failure()

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_configuration_connection_error(self) -> None:
        http_mock.register_exception(
            "POST",
            CONFIG_URL,
            exception=httpx2.ConnectError("Zammad unavailable"),
        )

        _, error = self.assert_zammad_failure()
        self.assertIsInstance(error.__cause__, httpx2.ConnectError)

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_submission_connection_error(self) -> None:
        http_mock.register(
            "POST",
            CONFIG_URL,
            json={"enabled": True, "endpoint": SUBMIT_URL, "token": "token"},
        )
        http_mock.register_exception(
            "POST",
            SUBMIT_URL,
            exception=httpx2.ConnectError("Zammad unavailable"),
        )

        _, error = self.assert_zammad_failure()
        self.assertIsInstance(error.__cause__, httpx2.ConnectError)

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_configuration_timeout(self) -> None:
        http_mock.register_exception(
            "POST",
            CONFIG_URL,
            exception=httpx2.ReadTimeout("Zammad timed out"),
        )

        _, error = self.assert_zammad_failure()
        self.assertIsInstance(error.__cause__, httpx2.ReadTimeout)

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_submission_timeout(self) -> None:
        http_mock.register(
            "POST",
            CONFIG_URL,
            json={"enabled": True, "endpoint": SUBMIT_URL, "token": "token"},
        )
        http_mock.register_exception(
            "POST",
            SUBMIT_URL,
            exception=httpx2.ReadTimeout("Zammad timed out"),
        )

        _, error = self.assert_zammad_failure()
        self.assertIsInstance(error.__cause__, httpx2.ReadTimeout)

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_http_error_with_zammad_errors(self) -> None:
        http_mock.register(
            "POST",
            CONFIG_URL,
            status_code=503,
            json={"errors": "Backend unavailable"},
        )

        report_error, error = self.assert_zammad_failure()
        self.assertNotIn("Backend unavailable", str(error))
        self.assertEqual(
            report_error.call_args.kwargs["extra_log"],
            "Zammad errors: 'Backend unavailable'",
        )

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_http_error_with_json(self) -> None:
        http_mock.register(
            "POST",
            CONFIG_URL,
            status_code=503,
            json={"detail": "Backend unavailable"},
        )

        self.assert_zammad_failure()

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_http_error_with_invalid_json(self) -> None:
        http_mock.register(
            "POST",
            CONFIG_URL,
            status_code=503,
            text="<html>Unavailable</html>",
        )

        self.assert_zammad_failure()

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_api_error_is_not_exposed(self) -> None:
        http_mock.register(
            "POST",
            CONFIG_URL,
            json={"errors": "Secret internal detail"},
        )

        report_error, error = self.assert_zammad_failure()
        self.assertNotIn("Secret internal detail", str(error))
        self.assertEqual(
            report_error.call_args.kwargs["extra_log"],
            "Zammad errors: 'Secret internal detail'",
        )

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_unexpected_json_type(self) -> None:
        http_mock.register("POST", CONFIG_URL, json=[])

        self.assert_zammad_failure()

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_disabled_configuration(self) -> None:
        http_mock.register("POST", CONFIG_URL, json={"enabled": False})

        self.assert_zammad_failure()

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_malformed_configuration(self) -> None:
        http_mock.register(
            "POST",
            CONFIG_URL,
            json={"enabled": True, "endpoint": SUBMIT_URL},
        )

        self.assert_zammad_failure()

    @override_settings(ZAMMAD_URL=ZAMMAD_URL)
    @http_mock.activate
    def test_malformed_ticket(self) -> None:
        http_mock.register(
            "POST",
            CONFIG_URL,
            json={"enabled": True, "endpoint": SUBMIT_URL, "token": "token"},
        )
        http_mock.register("POST", SUBMIT_URL, json={"ticket": {}})

        self.assert_zammad_failure()
