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


class ErrorCollectionSettingsTest(SimpleTestCase):
    @override_settings(
        SENTRY_DSN="https://public@example.com/1",
        GOOGLE_CLOUD_ERROR_REPORTING=None,
        OPENTELEMETRY_ENABLED=False,
    )
    def test_validate_error_collection_checks_sentry(self) -> None:
        with (
            patch(
                "weblate.utils.errors.get_sentry_sdk",
                side_effect=errors.ImproperlyConfigured("missing sentry"),
            ),
            self.assertRaisesMessage(
                errors.ImproperlyConfigured,
                "missing sentry",
            ),
        ):
            errors.validate_error_collection_settings()

    @override_settings(
        SENTRY_DSN=None,
        GOOGLE_CLOUD_ERROR_REPORTING={},
        OPENTELEMETRY_ENABLED=False,
    )
    def test_validate_error_collection_checks_google_cloud(self) -> None:
        with (
            patch(
                "weblate.utils.errors.get_google_cloud_error_reporting",
                side_effect=errors.ImproperlyConfigured("missing google"),
            ),
            self.assertRaisesMessage(
                errors.ImproperlyConfigured,
                "missing google",
            ),
        ):
            errors.validate_error_collection_settings()

    @override_settings(
        SENTRY_DSN=None,
        GOOGLE_CLOUD_ERROR_REPORTING=None,
        OPENTELEMETRY_ENABLED=False,
        ROLLBAR={},
    )
    def test_validate_error_collection_checks_rollbar(self) -> None:
        with (
            patch(
                "weblate.utils.errors.get_rollbar",
                side_effect=errors.ImproperlyConfigured("missing rollbar"),
            ),
            self.assertRaisesMessage(
                errors.ImproperlyConfigured,
                "missing rollbar",
            ),
        ):
            errors.validate_error_collection_settings()

    @override_settings(
        SENTRY_DSN=None,
        GOOGLE_CLOUD_ERROR_REPORTING=None,
        OPENTELEMETRY_ENABLED=True,
        OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT="http://collector:4318/v1/traces",
        OPENTELEMETRY_TRACES_SAMPLE_RATE=1.1,
    )
    def test_validate_error_collection_checks_opentelemetry(self) -> None:
        with self.assertRaisesMessage(
            errors.ImproperlyConfigured,
            "OPENTELEMETRY_TRACES_SAMPLE_RATE has to be between 0 and 1",
        ):
            errors.validate_error_collection_settings()

    @override_settings(
        SENTRY_DSN=None,
        GOOGLE_CLOUD_ERROR_REPORTING=None,
        OPENTELEMETRY_ENABLED=False,
    )
    def test_validate_error_collection_skips_unconfigured_backends(self) -> None:
        with (
            patch("weblate.utils.errors.get_sentry_sdk") as get_sentry_sdk,
            patch(
                "weblate.utils.errors.get_google_cloud_error_reporting"
            ) as get_google_cloud_error_reporting,
            patch("weblate.utils.errors.get_rollbar") as get_rollbar,
        ):
            errors.validate_error_collection_settings()

        get_sentry_sdk.assert_not_called()
        get_google_cloud_error_reporting.assert_not_called()
        get_rollbar.assert_not_called()


class GoogleCloudErrorReportingTest(SimpleTestCase):
    def tearDown(self) -> None:
        # ruff: ignore[private-member-access]
        errors._STATE["google_cloud_error_reporting_client"] = None
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
            # ruff: ignore[private-member-access]
            errors._STATE["google_cloud_error_reporting_client"],
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
    def test_report_message_without_sentry_does_not_import_sentry(self) -> None:
        with (
            patch("weblate.utils.errors.get_sentry_sdk") as get_sentry_sdk,
            patch("weblate.utils.errors.record_error"),
        ):
            errors.report_message("Handled error", level="error")

        get_sentry_sdk.assert_not_called()

    @override_settings(SENTRY_DSN=None)
    def test_report_message_without_rollbar_does_not_import_rollbar(self) -> None:
        with (
            patch("weblate.utils.errors.get_rollbar") as get_rollbar,
            patch("weblate.utils.errors.record_error"),
        ):
            errors.report_message("Handled error", level="error")

        get_rollbar.assert_not_called()

    @override_settings(SENTRY_DSN=None, ROLLBAR={})
    def test_report_message_uses_rollbar_when_configured(self) -> None:
        rollbar = MagicMock()

        with (
            patch("weblate.utils.errors.get_rollbar", return_value=rollbar),
            patch("weblate.utils.errors.record_error"),
        ):
            errors.report_message("Handled error", level="error")

        rollbar.report_message.assert_called_once_with("Handled error", level="error")
        rollbar.report_exc_info.assert_not_called()

    @override_settings(SENTRY_DSN=None)
    def test_report_error_reports_google_exception(self) -> None:
        client = MagicMock()
        # ruff: ignore[private-member-access]
        errors._STATE["google_cloud_error_reporting_client"] = client

        with patch("weblate.utils.errors.record_error"):
            try:
                raise_broken_error()
            except ValueError:
                errors.report_error("Handled error", level="error")

        report = client.report.call_args.args[0]
        self.assertIn("Traceback (most recent call last):", report)
        self.assertIn("ValueError: broken", report)
        client.report_exception.assert_not_called()

    @override_settings(SENTRY_DSN=None)
    def test_report_error_reports_explicit_google_exception(self) -> None:
        client = MagicMock()
        # ruff: ignore[private-member-access]
        errors._STATE["google_cloud_error_reporting_client"] = client
        handled_error: ValueError | None = None
        try:
            raise_broken_error()
        except ValueError as error:
            handled_error = error

        with patch("weblate.utils.errors.record_error"):
            errors.report_error(
                "Handled asynchronous error",
                level="error",
                exception=handled_error,
            )

        report = client.report.call_args.args[0]
        self.assertIn("Traceback (most recent call last):", report)
        self.assertIn("ValueError: broken", report)
        client.report_exception.assert_not_called()

    @override_settings(SENTRY_DSN="https://public@example.com/1")
    def test_report_message_reports_sentry_message(self) -> None:
        sentry_sdk = MagicMock()

        with (
            patch("weblate.utils.errors.get_sentry_sdk", return_value=sentry_sdk),
            patch("weblate.utils.errors.record_error"),
        ):
            errors.report_message("Handled error", level="error")

        sentry_sdk.capture_message.assert_called_once_with("Handled error")
        sentry_sdk.capture_exception.assert_not_called()

    @override_settings(SENTRY_DSN="https://public@example.com/1")
    def test_report_error_reports_sentry_exception(self) -> None:
        sentry_sdk = MagicMock()
        handled_error: ValueError | None = None

        with (
            patch("weblate.utils.errors.get_sentry_sdk", return_value=sentry_sdk),
            patch("weblate.utils.errors.record_error"),
        ):
            try:
                raise_broken_error()
            except ValueError as error:
                handled_error = error
                errors.report_error("Handled error", level="error")

        sentry_sdk.capture_exception.assert_called_once_with(handled_error)
        sentry_sdk.capture_message.assert_not_called()

    @override_settings(
        SENTRY_DSN="https://public@example.com/1",
        ROLLBAR={},
    )
    def test_report_error_preserves_explicit_exception(self) -> None:
        error = ValueError("async failure")
        sentry_sdk = MagicMock()
        rollbar = MagicMock()

        with (
            patch("weblate.utils.errors.get_sentry_sdk", return_value=sentry_sdk),
            patch("weblate.utils.errors.get_rollbar", return_value=rollbar),
            patch("weblate.utils.errors.record_error") as record_error,
        ):
            errors.report_error(
                "Handled asynchronous error",
                level="error",
                exception=error,
            )

        sentry_sdk.capture_exception.assert_called_once_with(error)
        rollbar.report_exc_info.assert_called_once_with(
            (ValueError, error, error.__traceback__),
            level="error",
        )
        self.assertIs(record_error.call_args.kwargs["exception"], error)

    @override_settings(SENTRY_DSN=None)
    def test_report_message_reports_google_message(self) -> None:
        client = MagicMock()
        # ruff: ignore[private-member-access]
        errors._STATE["google_cloud_error_reporting_client"] = client

        with patch("weblate.utils.errors.record_error"):
            errors.report_message("Handled error", level="error")

        client.report.assert_called_once_with("Handled error")
        client.report_exception.assert_not_called()

    @override_settings(SENTRY_DSN=None)
    def test_report_error_requires_exception(self) -> None:
        with self.assertRaisesMessage(
            RuntimeError, "report_error called without an exception: Handled error"
        ):
            errors.report_error("Handled error", level="error")

    @override_settings(SENTRY_DSN=None)
    def test_report_message_skip_error_reporting_skips_google(self) -> None:
        client = MagicMock()
        # ruff: ignore[private-member-access]
        errors._STATE["google_cloud_error_reporting_client"] = client

        with patch("weblate.utils.errors.record_error") as record_error:
            errors.report_message(
                "Handled error", level="error", skip_error_reporting=True
            )

        client.report.assert_not_called()
        client.report_exception.assert_not_called()
        record_error.assert_not_called()

    @override_settings(
        SENTRY_DSN="https://public@example.com/1",
        ROLLBAR={},
    )
    def test_report_message_ignores_ambient_exception(self) -> None:
        sentry_sdk = MagicMock()
        rollbar = MagicMock()
        google_client = MagicMock()
        # ruff: ignore[private-member-access]
        errors._STATE["google_cloud_error_reporting_client"] = google_client

        with (
            patch("weblate.utils.errors.get_sentry_sdk", return_value=sentry_sdk),
            patch("weblate.utils.errors.get_rollbar", return_value=rollbar),
            patch("weblate.utils.errors.record_error") as record_error,
            self.assertLogs(errors.ERROR_LOGGER, level="ERROR") as logs,
        ):
            try:
                raise_broken_error()
            except ValueError:
                errors.report_message("Handled message", level="error")

        sentry_sdk.capture_message.assert_called_once_with("Handled message")
        sentry_sdk.capture_exception.assert_not_called()
        rollbar.report_message.assert_called_once_with("Handled message", level="error")
        rollbar.report_exc_info.assert_not_called()
        google_client.report.assert_called_once_with("Handled message")
        self.assertIsNone(record_error.call_args.kwargs["exception"])
        self.assertEqual(logs.output, ["ERROR:weblate.errors:Handled message"])


class SentryScrubberTest(SimpleTestCase):
    @override_settings(
        SENTRY_DSN="https://public@example.com/1",
        SENTRY_SEND_PII=True,
    )
    def test_init_sentry_scrubs_passphrases_recursively(self) -> None:
        sentry_sdk = MagicMock()

        class ConfiguredScrubber:
            def __init__(self) -> None:
                self.called = False

            def scrub_event(self, event) -> None:
                self.called = True
                event["extra"] = {"BORG_PASSPHRASE": "custom-secret"}

        configured_scrubber = ConfiguredScrubber()

        with (
            override_settings(
                SENTRY_EXTRA_ARGS={"event_scrubber": configured_scrubber}
            ),
            patch("weblate.utils.errors.get_sentry_sdk", return_value=sentry_sdk),
        ):
            errors.init_sentry()

        scrubber = sentry_sdk.init.call_args.kwargs["event_scrubber"]
        borg_environment = {
            "BORG_PASSPHRASE": "borg-secret",
            "BORG_NEW_PASSPHRASE": "new-borg-secret",
            "SAFE": "visible",
        }
        frame_vars = {
            "password": "default-secret",
            "passphrase": "direct-secret",
            "env": borg_environment,
        }
        event = {
            "threads": {"values": [{"stacktrace": {"frames": [{"vars": frame_vars}]}}]}
        }

        scrubber.scrub_event(event)

        self.assertNotEqual(frame_vars["password"], "default-secret")
        self.assertNotEqual(frame_vars["passphrase"], "direct-secret")
        self.assertNotEqual(borg_environment["BORG_PASSPHRASE"], "borg-secret")
        self.assertNotEqual(borg_environment["BORG_NEW_PASSPHRASE"], "new-borg-secret")
        self.assertEqual(borg_environment["SAFE"], "visible")
        self.assertNotEqual(event["extra"]["BORG_PASSPHRASE"], "custom-secret")
        self.assertTrue(configured_scrubber.called)
