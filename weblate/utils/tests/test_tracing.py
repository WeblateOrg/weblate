# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings
from opentelemetry.trace import StatusCode

from weblate.utils import errors, tracing


def raise_broken_error() -> None:
    msg = "broken"
    raise ValueError(msg)


@override_settings(TEST_RAISE_REPORT_ERROR=False)
class TracingTest(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        tracing.configure_opentelemetry_tracer(None)
        # ruff: ignore[private-member-access]
        errors._STATE["opentelemetry_at_fork_registered"] = False
        # ruff: ignore[private-member-access]
        errors._STATE["opentelemetry_initialized_pid"] = None
        # ruff: ignore[private-member-access]
        errors._STATE["opentelemetry_provider"] = None

    def tearDown(self) -> None:
        tracing.configure_opentelemetry_tracer(None)
        # ruff: ignore[private-member-access]
        errors._STATE["opentelemetry_at_fork_registered"] = False
        # ruff: ignore[private-member-access]
        errors._STATE["opentelemetry_initialized_pid"] = None
        # ruff: ignore[private-member-access]
        errors._STATE["opentelemetry_provider"] = None
        super().tearDown()

    @override_settings(SENTRY_DSN=None)
    def test_start_span_disabled(self) -> None:
        with (
            patch("weblate.utils.tracing.get_sentry_sdk") as get_sentry_sdk,
            tracing.start_span("test.op", "Test span"),
        ):
            pass

        get_sentry_sdk.assert_not_called()

    @override_settings(SENTRY_DSN=None)
    def test_report_error_records_opentelemetry(self) -> None:
        handled_error: ValueError | None = None
        with patch("weblate.utils.errors.record_error") as record_error:
            try:
                raise_broken_error()
            except ValueError as error:
                handled_error = error
                errors.report_error("Handled error", level="error")

        record_error.assert_called_once()
        self.assertEqual(record_error.call_args.args, ("Handled error",))
        self.assertEqual(record_error.call_args.kwargs["level"], "error")
        self.assertIs(record_error.call_args.kwargs["exception"], handled_error)

    @override_settings(SENTRY_DSN=None)
    def test_report_error_skip_error_reporting_skips_opentelemetry(self) -> None:
        with patch("weblate.utils.errors.record_error") as record_error:
            errors.report_error(
                "Handled error", level="error", skip_error_reporting=True
            )

        record_error.assert_not_called()

    @override_settings(SENTRY_DSN="https://public@example.com/1")
    def test_start_span_uses_configured_backends(self) -> None:
        sentry_context = MagicMock()
        sentry_span = MagicMock()
        sentry_span.set_attribute = MagicMock()
        otel_context = MagicMock()
        otel_context.__enter__.return_value = sentry_span
        tracer = MagicMock()
        tracer.start_as_current_span.return_value = otel_context

        tracing.configure_opentelemetry_tracer(tracer)
        sentry_sdk = MagicMock()
        sentry_sdk.start_span.return_value = sentry_context

        with (
            patch("weblate.utils.tracing.get_sentry_sdk", return_value=sentry_sdk),
            tracing.start_span("test.op", "Test span", extra=42),
        ):
            pass

        sentry_sdk.start_span.assert_called_once_with(op="test.op", name="Test span")
        tracer.start_as_current_span.assert_called_once_with("test.op")
        sentry_span.set_attribute.assert_any_call("weblate.operation", "test.op")
        sentry_span.set_attribute.assert_any_call("weblate.name", "Test span")
        sentry_span.set_attribute.assert_any_call("extra", 42)

    def test_record_error_annotates_current_span(self) -> None:
        tracer = MagicMock()
        span = MagicMock()
        span.is_recording.return_value = True
        error = ValueError("broken")

        tracing.configure_opentelemetry_tracer(tracer)

        with patch("opentelemetry.trace.get_current_span", return_value=span):
            tracing.record_error(
                "Handled error",
                level="error",
                exception=error,
                attributes={"weblate.project": "project"},
            )

        span.record_exception.assert_called_once_with(
            error,
            attributes={
                "weblate.error.cause": "Handled error",
                "weblate.error.level": "error",
                "weblate.project": "project",
            },
        )
        self.assertEqual(
            span.set_status.call_args.args[0].status_code, StatusCode.ERROR
        )
        tracer.start_as_current_span.assert_not_called()

    def test_record_error_creates_span_without_current_span(self) -> None:
        current_span = MagicMock()
        current_span.is_recording.return_value = False
        report_span = MagicMock()
        report_context = MagicMock()
        report_context.__enter__.return_value = report_span
        tracer = MagicMock()
        tracer.start_as_current_span.return_value = report_context

        tracing.configure_opentelemetry_tracer(tracer)

        with patch("opentelemetry.trace.get_current_span", return_value=current_span):
            tracing.record_error("Handled message", level="warning")

        tracer.start_as_current_span.assert_called_once_with("weblate.report_error")
        report_span.add_event.assert_called_once_with(
            "weblate.error",
            attributes={
                "weblate.error.cause": "Handled message",
                "weblate.error.level": "warning",
            },
        )
        report_span.set_status.assert_not_called()

    def test_record_error_suppresses_opentelemetry_errors(self) -> None:
        with (
            patch(
                "weblate.utils.tracing._record_error", side_effect=RuntimeError("boom")
            ),
            self.assertLogs("weblate.tracing", level="ERROR") as logs,
        ):
            tracing.record_error("Handled error", level="error")

        self.assertIn("Could not record OpenTelemetry error", logs.output[0])

    @override_settings(
        OPENTELEMETRY_ENABLED=False,
        OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT="http://collector:4318/v1/traces",
    )
    def test_init_opentelemetry_disabled(self) -> None:
        with patch(
            "weblate.utils.tracing.configure_opentelemetry_tracer"
        ) as configure_tracer:
            errors.init_opentelemetry()

        configure_tracer.assert_called_once_with(None)

    @override_settings(
        OPENTELEMETRY_ENABLED=True,
        OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT="http://collector:4318/v1/traces",
        OPENTELEMETRY_TRACES_SAMPLE_RATE=0,
    )
    def test_init_opentelemetry_zero_sample_rate_disables_tracing(self) -> None:
        with (
            patch(
                "weblate.utils.tracing.configure_opentelemetry_tracer"
            ) as configure_tracer,
            patch(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
            ) as exporter,
        ):
            errors.init_opentelemetry()

        configure_tracer.assert_called_once_with(None)
        exporter.assert_not_called()

    @override_settings(
        OPENTELEMETRY_ENABLED=True,
        OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT="http://collector:4318/v1/traces",
        OPENTELEMETRY_TRACES_SAMPLE_RATE=1.1,
    )
    def test_init_opentelemetry_rejects_invalid_sample_rate(self) -> None:
        with self.assertRaisesMessage(
            errors.ImproperlyConfigured,
            "OPENTELEMETRY_TRACES_SAMPLE_RATE has to be between 0 and 1",
        ):
            errors.init_opentelemetry()

    @override_settings(
        OPENTELEMETRY_ENABLED=True,
        OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT="http://collector:4318/v1/traces",
        OPENTELEMETRY_EXPORTER_OTLP_HEADERS={"authorization": "Bearer test"},
        OPENTELEMETRY_SERVICE_NAME="weblate-test",
        OPENTELEMETRY_TRACES_SAMPLE_RATE=0.5,
        OPENTELEMETRY_EXTRA_RESOURCE_ATTRIBUTES={"service.namespace": "tests"},
        SENTRY_ENVIRONMENT="test",
    )
    def test_init_opentelemetry_configures_exporter(self) -> None:
        with (
            patch(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
            ) as exporter,
            patch("opentelemetry.sdk.resources.Resource.create") as resource_create,
            patch("opentelemetry.sdk.trace.TracerProvider") as tracer_provider,
            patch("opentelemetry.sdk.trace.export.BatchSpanProcessor") as processor,
            patch("opentelemetry.sdk.trace.sampling.TraceIdRatioBased") as sampler,
            patch("opentelemetry.instrumentation.django.DjangoInstrumentor") as django,
            patch("opentelemetry.instrumentation.celery.CeleryInstrumentor") as celery,
            patch("opentelemetry.instrumentation.redis.RedisInstrumentor") as redis,
            patch(
                "opentelemetry.instrumentation.requests.RequestsInstrumentor"
            ) as requests,
            patch(
                "opentelemetry.instrumentation.psycopg.PsycopgInstrumentor"
            ) as psycopg,
            patch(
                "weblate.utils.tracing.configure_opentelemetry_tracer"
            ) as configure_tracer,
            patch("weblate.utils.errors.os.register_at_fork") as register_at_fork,
        ):
            tracer_provider.return_value.get_tracer.return_value = "tracer"
            for instrumentor in (django, celery, redis, requests, psycopg):
                instrumentor.return_value.is_instrumented_by_opentelemetry = False
            errors.init_opentelemetry()

        exporter.assert_called_once_with(
            endpoint="http://collector:4318/v1/traces",
            headers={"authorization": "Bearer test"},
        )
        sampler.assert_called_once_with(0.5)
        resource_create.assert_called_once()
        self.assertEqual(
            resource_create.call_args.args[0]["service.name"], "weblate-test"
        )
        self.assertEqual(
            resource_create.call_args.args[0]["deployment.environment"], "test"
        )
        self.assertEqual(
            resource_create.call_args.args[0]["service.namespace"], "tests"
        )
        tracer_provider.return_value.add_span_processor.assert_called_once_with(
            processor.return_value
        )
        tracer_provider.return_value.get_tracer.assert_called_once()
        configure_tracer.assert_called_once_with("tracer")
        register_at_fork.assert_called_once_with(
            # ruff: ignore[private-member-access]
            after_in_child=errors._init_opentelemetry_after_fork
        )
        for instrumentor in (django, celery, redis, requests, psycopg):
            instrumentor.return_value.instrument.assert_called_once_with(
                tracer_provider=tracer_provider.return_value
            )

    def test_init_opentelemetry_after_fork_resets_state(self) -> None:
        # ruff: ignore[private-member-access]
        errors._STATE["opentelemetry_initialized_pid"] = 100
        # ruff: ignore[private-member-access]
        errors._STATE["opentelemetry_provider"] = object()

        with patch("weblate.utils.errors.init_opentelemetry") as init_opentelemetry:
            # ruff: ignore[private-member-access]
            errors._init_opentelemetry_after_fork()

        # ruff: ignore[private-member-access]
        self.assertIsNone(errors._STATE["opentelemetry_initialized_pid"])
        # ruff: ignore[private-member-access]
        self.assertIsNone(errors._STATE["opentelemetry_provider"])
        init_opentelemetry.assert_called_once_with()

    @override_settings(
        OPENTELEMETRY_ENABLED=True,
        OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT="http://collector:4318/v1/traces",
        OPENTELEMETRY_EXPORTER_OTLP_HEADERS={},
        OPENTELEMETRY_SERVICE_NAME="weblate-test",
        OPENTELEMETRY_TRACES_SAMPLE_RATE=1,
        OPENTELEMETRY_EXTRA_RESOURCE_ATTRIBUTES={},
        SENTRY_ENVIRONMENT="test",
    )
    def test_init_opentelemetry_reinitializes_after_fork(self) -> None:
        first_provider = MagicMock()
        second_provider = MagicMock()

        with (
            patch(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
            ),
            patch("opentelemetry.sdk.resources.Resource.create"),
            patch(
                "opentelemetry.sdk.trace.TracerProvider",
                side_effect=[first_provider, second_provider],
            ) as tracer_provider,
            patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
            patch("opentelemetry.sdk.trace.sampling.TraceIdRatioBased"),
            patch("opentelemetry.instrumentation.django.DjangoInstrumentor") as django,
            patch("opentelemetry.instrumentation.celery.CeleryInstrumentor") as celery,
            patch("opentelemetry.instrumentation.redis.RedisInstrumentor") as redis,
            patch(
                "opentelemetry.instrumentation.requests.RequestsInstrumentor"
            ) as requests,
            patch(
                "opentelemetry.instrumentation.psycopg.PsycopgInstrumentor"
            ) as psycopg,
            patch("weblate.utils.errors.os.getpid", side_effect=[100, 101]),
            patch("weblate.utils.errors.os.register_at_fork") as register_at_fork,
        ):
            for instrumentor in (django, celery, redis, requests, psycopg):
                instrumentor.return_value.is_instrumented_by_opentelemetry = False
            errors.init_opentelemetry()
            errors.init_opentelemetry()

        self.assertEqual(tracer_provider.call_count, 2)
        register_at_fork.assert_called_once_with(
            # ruff: ignore[private-member-access]
            after_in_child=errors._init_opentelemetry_after_fork
        )
        first_provider.shutdown.assert_called_once_with()
        second_provider.shutdown.assert_not_called()
