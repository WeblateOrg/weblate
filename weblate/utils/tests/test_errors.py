# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from weblate.utils import errors


def raise_broken_error() -> None:
    msg = "broken"
    raise ValueError(msg)


class GoogleCloudErrorReportingTest(SimpleTestCase):
    def tearDown(self) -> None:
        errors._STATE["google_cloud_error_reporting_client"] = None  # noqa: SLF001
        super().tearDown()

    @override_settings(GOOGLE_CLOUD_ERROR_REPORTING={})
    def test_init_google_cloud_error_reporting_uses_defaults(self) -> None:
        reporting = MagicMock()

        with (
            patch.object(
                errors, "get_google_cloud_error_reporting", return_value=reporting
            ),
            patch("weblate.utils.version.GIT_REVISION", "revision"),
            patch("weblate.utils.version.TAG_NAME", "tag"),
        ):
            errors.init_google_cloud_error_reporting()

        reporting.Client.assert_called_once_with(service="weblate", version="revision")
        self.assertEqual(
            errors._STATE["google_cloud_error_reporting_client"],  # noqa: SLF001
            reporting.Client.return_value,
        )

    @override_settings(
        GOOGLE_CLOUD_ERROR_REPORTING={
            "project": "test-project",
            "service": "custom-service",
            "version": "custom-version",
        }
    )
    def test_init_google_cloud_error_reporting_allows_overrides(self) -> None:
        reporting = MagicMock()

        with patch.object(
            errors, "get_google_cloud_error_reporting", return_value=reporting
        ):
            errors.init_google_cloud_error_reporting()

        reporting.Client.assert_called_once_with(
            project="test-project",
            service="custom-service",
            version="custom-version",
        )

    @override_settings(SENTRY_DSN=None)
    def test_report_error_without_sentry_does_not_import_sentry(self) -> None:
        with (
            patch("weblate.utils.errors.get_sentry_sdk") as get_sentry_sdk,
            patch("weblate.utils.errors.record_error"),
        ):
            errors.report_error("Handled error", level="error", message=True)

        get_sentry_sdk.assert_not_called()

    @override_settings(SENTRY_DSN=None)
    def test_report_error_without_rollbar_does_not_import_rollbar(self) -> None:
        with (
            patch("weblate.utils.errors.get_rollbar") as get_rollbar,
            patch("weblate.utils.errors.record_error"),
        ):
            errors.report_error("Handled error", level="error", message=True)

        get_rollbar.assert_not_called()

    @override_settings(SENTRY_DSN=None, ROLLBAR={})
    def test_report_error_uses_rollbar_when_configured(self) -> None:
        rollbar = MagicMock()

        with (
            patch("weblate.utils.errors.get_rollbar", return_value=rollbar),
            patch("weblate.utils.errors.record_error"),
        ):
            errors.report_error("Handled error", level="error", message=True)

        rollbar.report_exc_info.assert_called_once_with(level="error")

    @override_settings(SENTRY_DSN=None)
    def test_report_error_reports_google_exception(self) -> None:
        client = MagicMock()
        errors._STATE["google_cloud_error_reporting_client"] = client  # noqa: SLF001

        with patch("weblate.utils.errors.record_error"):
            try:
                raise_broken_error()
            except ValueError:
                errors.report_error("Handled error", level="error")

        client.report_exception.assert_called_once_with()
        client.report.assert_not_called()

    @override_settings(SENTRY_DSN="https://public@example.com/1")
    def test_report_error_reports_sentry_message_without_exception(self) -> None:
        sentry_sdk = MagicMock()

        with (
            patch("weblate.utils.errors.get_sentry_sdk", return_value=sentry_sdk),
            patch("weblate.utils.errors.record_error"),
        ):
            errors.report_error("Handled error", level="error")

        sentry_sdk.capture_message.assert_called_once_with("Handled error")
        sentry_sdk.capture_exception.assert_not_called()

    @override_settings(SENTRY_DSN="https://public@example.com/1")
    def test_report_error_reports_sentry_exception(self) -> None:
        sentry_sdk = MagicMock()

        with (
            patch("weblate.utils.errors.get_sentry_sdk", return_value=sentry_sdk),
            patch("weblate.utils.errors.record_error"),
        ):
            try:
                raise_broken_error()
            except ValueError:
                errors.report_error("Handled error", level="error")

        sentry_sdk.capture_exception.assert_called_once_with()
        sentry_sdk.capture_message.assert_not_called()

    @override_settings(SENTRY_DSN=None)
    def test_report_error_reports_google_message(self) -> None:
        client = MagicMock()
        errors._STATE["google_cloud_error_reporting_client"] = client  # noqa: SLF001

        with patch("weblate.utils.errors.record_error"):
            errors.report_error("Handled error", level="error", message=True)

        client.report.assert_called_once_with("Handled error")
        client.report_exception.assert_not_called()

    @override_settings(SENTRY_DSN=None)
    def test_report_error_reports_google_message_without_exception(self) -> None:
        client = MagicMock()
        errors._STATE["google_cloud_error_reporting_client"] = client  # noqa: SLF001

        with patch("weblate.utils.errors.record_error"):
            errors.report_error("Handled error", level="error")

        client.report.assert_called_once_with("Handled error")
        client.report_exception.assert_not_called()

    @override_settings(SENTRY_DSN=None)
    def test_report_error_skip_error_reporting_skips_google(self) -> None:
        client = MagicMock()
        errors._STATE["google_cloud_error_reporting_client"] = client  # noqa: SLF001

        with patch("weblate.utils.errors.record_error") as record_error:
            errors.report_error(
                "Handled error", level="error", skip_error_reporting=True
            )

        client.report.assert_not_called()
        client.report_exception.assert_not_called()
        record_error.assert_not_called()
