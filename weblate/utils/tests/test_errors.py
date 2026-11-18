# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from asyncio import run
from base64 import b64encode
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpcore2
import httpx2
from django.test import SimpleTestCase, override_settings
from sentry_sdk import Client
from sentry_sdk.integrations.httpx2 import Httpx2Integration
from sentry_sdk.transport import Transport

from weblate.machinery.google import GoogleTranslation
from weblate.machinery.yandex import YandexTranslation
from weblate.utils import errors
from weblate.vcs.git import GitRepository
from weblate.vcs.github import (
    GitHubAppCredentials,
    exchange_github_user_code,
    get_app_installation,
    get_app_repositories,
    get_github_git_auth_environment,
)
from weblate.vcs.tests.utils import generate_private_key

if TYPE_CHECKING:
    from sentry_sdk._types import Event, Hint
    from sentry_sdk.envelope import Envelope


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


class SentryBeforeSendTest(SimpleTestCase):
    def test_normal_event_is_unchanged(self) -> None:
        event: Event = {"exception": {"values": [{"type": "ValueError"}]}}
        original = json.dumps(event)
        self.assertIs(errors.SentryBeforeSend()(event, {}), event)
        self.assertEqual(json.dumps(event), original)

    def test_configured_filter_can_drop_event(self) -> None:
        callback = MagicMock(return_value=None)
        event: Event = {"message": "filtered"}
        hint: Hint = {}
        self.assertIsNone(errors.SentryBeforeSend(callback)(event, hint))
        callback.assert_called_once_with(event, hint)

    def test_configured_callback_can_replace_event(self) -> None:
        replacement: Event = {
            "message": "https://example.com/?token=callback-secret",
            "extra": {
                "client_secret": "callback-secret",
                "headers": (
                    {"Set-Cookie": "cookie-secret"},
                    ("Authorization", "Bearer tuple-secret"),
                ),
                "urls": (
                    "amqp://user:broker-secret@broker.example/vhost",
                    "https://user:apostrophe'secret@example.com/path",
                ),
            },
        }
        callback = MagicMock(return_value=replacement)
        self.assertIs(errors.SentryBeforeSend(callback)({}, {}), replacement)
        captured = json.dumps(replacement)
        for secret in (
            "callback-secret",
            "cookie-secret",
            "tuple-secret",
            "broker-secret",
            "apostrophe'secret",
        ):
            self.assertNotIn(secret, captured)
        self.assertIn("broker.example/vhost", captured)
        self.assertIn("example.com/path", captured)

    def test_large_exception_chain_is_captured(self) -> None:
        events: list[Event] = []

        class CollectingTransport(Transport):
            def capture_envelope(self, envelope: Envelope) -> None:
                for item in envelope.items:
                    event = item.get_event()
                    if event is not None:
                        events.append(event)

        sentry_sdk = errors.get_sentry_sdk()
        client = sentry_sdk.Client(
            dsn="https://public@example.com/1",
            transport=CollectingTransport,
            default_integrations=False,
            auto_enabling_integrations=False,
            before_send=errors.SentryBeforeSend(),
            max_value_length=10_000,
        )
        self.addCleanup(client.close)
        error: BaseException = OSError("original filesystem error")
        for _ in range(250):
            previous = error
            error = OSError("Directory not empty: " + "x" * 8192)
            error.__context__ = previous
        final_error = RecursionError("maximum recursion depth exceeded")
        final_error.__context__ = error

        with sentry_sdk.isolation_scope() as scope:
            scope.set_client(client)
            scope.set_tag("celery_task_id", "upload-task")
            scope.set_extra("celery-job", {"task_name": "translation_upload"})
            self.assertIsNotNone(sentry_sdk.capture_exception(final_error))

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertLess(len(json.dumps(event).encode()), 1_000_000)
        values = event["exception"]["values"]
        self.assertEqual(values[0]["value"], "original filesystem error")
        self.assertEqual(values[-1]["type"], "RecursionError")
        self.assertEqual(event["tags"]["celery_task_id"], "upload-task")
        self.assertEqual(
            cast("dict[str, str]", event["extra"]["celery-job"])["task_name"],
            "translation_upload",
        )
        self.assertEqual(
            event["contexts"]["weblate_exception_chain"]["omitted_count"],
            252 - len(values),
        )

    def test_exception_group_hierarchy_is_preserved(self) -> None:
        event = cast(
            "Event",
            {
                "exception": {
                    "values": [
                        {
                            "value": "x" * 400_000,
                            "mechanism": {"exception_id": index},
                        }
                        for index in range(3)
                    ]
                }
            },
        )
        self.assertIs(errors.SentryBeforeSend()(event, {}), event)
        self.assertEqual(len(event["exception"]["values"]), 3)

    def test_shortening_chain_removes_stale_annotations(self) -> None:
        event = cast(
            "Event",
            {
                "exception": {"values": [{"value": "x" * 60_000} for _ in range(20)]},
                "_meta": {
                    "exception": {"values": {"10": {"value": {"": {"len": 100}}}}},
                    "extra": {"diagnostic": {"": {"len": 100}}},
                },
            },
        )
        errors.SentryBeforeSend()(event, {})
        metadata = cast("dict[str, object]", event.get("_meta"))
        self.assertNotIn("exception", metadata)
        self.assertIn("extra", metadata)

    @override_settings(SENTRY_DSN="https://public@example.com/1")
    def test_init_sentry_wraps_configured_callback(self) -> None:
        for option in ("before_send", "before_send_transaction"):
            with self.subTest(option=option):
                callback = MagicMock(return_value=None)
                sentry_sdk = MagicMock()
                with (
                    override_settings(SENTRY_EXTRA_ARGS={option: callback}),
                    patch(
                        "weblate.utils.errors.get_sentry_sdk", return_value=sentry_sdk
                    ),
                ):
                    errors.init_sentry()
                before_send = sentry_sdk.init.call_args.kwargs[option]
                self.assertIsNone(before_send({}, {}))
                callback.assert_called_once_with({}, {})


class SentryScrubberTest(SimpleTestCase):
    def create_client(self, events: list[Event]) -> Client:
        class CollectingTransport(Transport):
            def capture_envelope(self, envelope: Envelope) -> None:
                for item in envelope.items:
                    event = item.get_event() or item.get_transaction_event()
                    if event is not None:
                        events.append(event)

        mocked_sdk = MagicMock()
        with (
            override_settings(SENTRY_SEND_PII=True, SENTRY_EXTRA_ARGS={}),
            patch("weblate.utils.errors.get_sentry_sdk", return_value=mocked_sdk),
        ):
            errors.init_sentry()
        options = mocked_sdk.init.call_args.kwargs
        client = Client(
            dsn="https://public@example.com/1",
            event_scrubber=options["event_scrubber"],
            before_send=options["before_send"],
            before_send_transaction=options["before_send_transaction"],
            default_integrations=False,
            auto_enabling_integrations=False,
            integrations=[Httpx2Integration()],
            transport=CollectingTransport,
            traces_sample_rate=1,
        )
        self.addCleanup(client.close)
        return client

    def test_git_auth_environment_is_scrubbed_from_captured_exceptions(self) -> None:
        events: list[Event] = []
        sentry_sdk = errors.get_sentry_sdk()
        secret = "synthetic-git-auth-secret"
        credentials = b64encode(f"x-access-token:{secret}".encode()).decode()
        client = self.create_client(events)
        with (
            sentry_sdk.isolation_scope() as scope,
            patch(
                "weblate.vcs.base.subprocess.run",
                side_effect=OSError("synthetic subprocess failure"),
            ),
        ):
            scope.set_client(client)
            try:
                GitRepository._popen(  # ruff: ignore[private-member-access]
                    ["fetch"],
                    local=True,
                    environment=get_github_git_auth_environment(
                        "x-access-token", secret
                    ),
                )
            except OSError as error:
                sentry_sdk.capture_exception(error)
            self.assertEqual(len(events), 1)
            captured = json.dumps(events[0])
            self.assertNotIn(secret, captured)
            self.assertNotIn(credentials, captured)
            self.assertIn("http.extraHeader", captured)
            self.assertIn("synthetic subprocess failure", captured)

    def test_http_auth_buffers_are_scrubbed_from_captured_exceptions(self) -> None:
        events: list[Event] = []
        sentry_sdk = errors.get_sentry_sdk()
        secret = uuid4().hex
        provider = GoogleTranslation({"key": secret, "_installation_id": 123})

        async def capture_failure() -> None:
            try:
                await provider.arequest("post", "https://translation.googleapis.com/")
            except httpx2.WriteTimeout as error:
                sentry_sdk.capture_exception(error)

        client = self.create_client(events)
        with (
            sentry_sdk.isolation_scope() as scope,
            patch(
                "weblate.machinery.base.get_site_url",
                return_value="https://example.com/",
            ),
            patch(
                "weblate.utils.requests._TEST_TRANSPORT.transport",
                httpx2.AsyncHTTPTransport(),
            ),
            patch(
                "httpcore2._backends.auto.AutoBackend.connect_tcp",
                new=AsyncMock(return_value=httpcore2.AsyncMockStream([])),
            ),
            patch(
                "httpcore2._backends.mock.AsyncMockStream.write",
                new=AsyncMock(
                    side_effect=httpcore2.WriteTimeout("synthetic write timeout")
                ),
            ),
        ):
            scope.set_client(client)
            run(capture_failure())
            self.assertEqual(len(events), 1)
            self.assertNotIn(secret, json.dumps(events[0]))
            self.assertIn("HTTP/1.1", json.dumps(events[0]))
            self.assertIn("translation.googleapis.com", json.dumps(events[0]))
            self.assertIn("synthetic write timeout", json.dumps(events[0]))

    def test_github_credentials_are_scrubbed_from_captured_exceptions(self) -> None:
        events: list[Event] = []
        sentry_sdk = errors.get_sentry_sdk()
        private_key = generate_private_key()
        client_secret = "synthetic-github-client-secret"
        access_token = "synthetic-github-access-token"
        config = GitHubAppCredentials(
            hostname="github.com", client_id="test-client", client_secret=client_secret
        )

        async def fetch() -> None:
            if operation == "installation":
                await get_app_installation(123, private_key, 123, "github.com")
            elif operation == "oauth":
                await exchange_github_user_code(config, "dummy-code")
            else:
                await get_app_repositories(123, private_key, 123, "github.com")

        async def capture_failure() -> None:
            try:
                await fetch()
            except RuntimeError as error:
                sentry_sdk.capture_exception(error)

        client = self.create_client(events)
        for operation in ("installation", "oauth", "repositories"):
            with (
                self.subTest(operation=operation),
                sentry_sdk.isolation_scope() as scope,
                patch(
                    "weblate.vcs.github.async_fetch_validated_url",
                    new=AsyncMock(side_effect=RuntimeError("offline GitHub failure")),
                ),
                patch(
                    "weblate.vcs.github.get_installation_token",
                    new=AsyncMock(return_value=access_token),
                ),
            ):
                events.clear()
                scope.set_client(client)
                run(capture_failure())
                self.assertEqual(len(events), 1)
                captured = json.dumps(events[0])
                self.assertNotIn(client_secret, captured)
                self.assertNotIn(access_token, captured)
                self.assertNotIn(private_key.splitlines()[2], captured)
                self.assertIn("offline GitHub failure", captured)

    def test_query_credentials_are_scrubbed_after_http_capture(self) -> None:
        events: list[Event] = []
        sentry_sdk = errors.get_sentry_sdk()
        secret = "synthetic-yandex-credential"
        provider = YandexTranslation({"key": secret, "_installation_id": 123})

        def handle_request(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(
                400, json={"message": "provider failure"}, request=request
            )

        async def capture_failure() -> None:
            try:
                await provider.arequest(
                    "get", "https://example.com/", params={"key": secret, "lang": "en"}
                )
            except httpx2.HTTPStatusError as error:
                sentry_sdk.capture_exception(error)

        client = self.create_client(events)
        with (
            sentry_sdk.isolation_scope() as scope,
            patch(
                "weblate.machinery.base.get_site_url",
                return_value="https://example.com/",
            ),
            patch(
                "weblate.utils.requests._TEST_TRANSPORT.transport",
                httpx2.MockTransport(handle_request),
            ),
        ):
            scope.set_client(client)
            with sentry_sdk.start_transaction(name="machinery request", op="test"):
                run(capture_failure())
            self.assertEqual(len(events), 2)
            self.assertNotIn(secret, json.dumps(events))
            error_event = events[0]
            transaction = events[1]
            self.assertEqual(transaction["type"], "transaction")
            self.assertTrue(transaction["spans"])
            self.assertIn("key=[Filtered]&lang=en", json.dumps(transaction))
            self.assertIn("key=[Filtered]&lang=en", json.dumps(error_event))
            self.assertTrue(
                cast("dict[str, object]", error_event["breadcrumbs"])["values"]
            )

    @override_settings(
        SENTRY_DSN="https://public@example.com/1",
        SENTRY_SEND_PII=True,
    )
    def test_init_sentry_scrubs_passphrases_recursively(self) -> None:
        sentry_sdk = MagicMock()

        class ConfiguredScrubber:
            def __init__(self) -> None:
                self.called = False

            def scrub_event(self, event: Event) -> None:
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
