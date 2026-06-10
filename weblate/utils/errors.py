# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
import os
import sys
from contextlib import suppress
from importlib import import_module
from json import JSONDecodeError
from typing import TYPE_CHECKING, Any, Literal, cast

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import get_language

import weblate.utils.version
from weblate.utils.tracing import record_error

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest

ERROR_LOGGER = "weblate.errors"

LOGGER = logging.getLogger(ERROR_LOGGER)
_STATE: dict[str, Any] = {
    "google_cloud_error_reporting_client": None,
    "opentelemetry_at_fork_registered": False,
    "opentelemetry_initialized_pid": None,
    "opentelemetry_provider": None,
}


def get_sentry_sdk():
    try:
        return import_module("sentry_sdk")
    except ImportError as error:
        msg = "sentry-sdk has to be installed to use SENTRY_DSN"
        raise ImproperlyConfigured(msg) from error


def get_google_cloud_error_reporting():
    try:
        return import_module("google.cloud.error_reporting")
    except ImportError as error:
        msg = (
            "google-cloud-error-reporting has to be installed to use "
            "GOOGLE_CLOUD_ERROR_REPORTING"
        )
        raise ImproperlyConfigured(msg) from error


def get_rollbar():
    try:
        return import_module("rollbar")
    except ImportError as error:
        msg = "rollbar has to be installed to use ROLLBAR"
        raise ImproperlyConfigured(msg) from error


def report_error(
    cause: str,
    *,
    level: Literal[
        "fatal", "critical", "error", "warning", "info", "debug"
    ] = "warning",
    skip_error_reporting: bool = False,
    print_tb: bool = False,
    extra_log: str | None = None,
    project=None,
    message: bool = False,
) -> None:
    """
    Report errors.

    This can be used for store exceptions in error reporting solutions as rollbar while
    handling error gracefully and giving user cleaner message.
    """
    # pylint: disable-next=unused-variable
    __traceback_hide__ = True  # noqa: F841
    error = sys.exc_info()[1]
    locale = get_language()
    report_as_message = message or error is None

    if not skip_error_reporting:
        if hasattr(settings, "ROLLBAR"):
            rollbar = get_rollbar()
            rollbar.report_exc_info(level=level)

        if settings.SENTRY_DSN:
            sentry_sdk = get_sentry_sdk()
            sentry_sdk.set_tag("cause", cause)
            if project is not None:
                sentry_sdk.set_tag("project", project.slug)
            sentry_sdk.set_tag("user.locale", locale)
            sentry_sdk.set_level(level)
            if report_as_message:
                sentry_sdk.capture_message(cause)
            else:
                sentry_sdk.capture_exception()

        google_client = _STATE["google_cloud_error_reporting_client"]
        if google_client is not None:
            if report_as_message:
                google_client.report(cause)
            else:
                google_client.report_exception()

        record_error(
            cause,
            level=level,
            exception=None if report_as_message else error,
            attributes={
                "weblate.project": None if project is None else project.slug,
                "weblate.user_locale": locale,
            },
        )

    _log_error(cause, level=level, extra_log=extra_log, print_tb=print_tb)


def _log_error(
    cause: str,
    *,
    level: Literal[
        "fatal", "critical", "error", "warning", "info", "debug"
    ] = "warning",
    extra_log: str | None = None,
    print_tb: bool = False,
) -> None:
    """Log the current exception without reporting it to external services."""
    log = getattr(LOGGER, level)
    error = sys.exc_info()[1]

    # Include JSON document if available. It might be missing
    # when the error is raised from requests.
    if isinstance(error, JSONDecodeError) and not extra_log and hasattr(error, "doc"):
        extra_log = repr(error.doc)

    if error:
        log("%s: %s: %s", cause, error.__class__.__name__, error)
    if extra_log:
        if error:
            log("%s: %s: %s", cause, error.__class__.__name__, extra_log)
        else:
            log("%s: %s", cause, extra_log)
    if print_tb:
        # This is called from an exception handler
        LOGGER.exception(cause)  # noqa: LOG004


def log_handled_exception(
    cause: str,
    *,
    level: Literal[
        "fatal", "critical", "error", "warning", "info", "debug"
    ] = "warning",
    extra_log: str | None = None,
) -> None:
    """Log a handled exception without reporting it to Sentry or Rollbar."""
    _log_error(cause, level=level, extra_log=extra_log)


def add_breadcrumb(category: str, message: str, level: str = "info", **data) -> None:
    # Add breadcrumb only if settings are already loaded,
    # we do not want to force loading settings early
    if not settings.configured or not getattr(settings, "SENTRY_DSN", None):
        return
    sentry_sdk = get_sentry_sdk()
    sentry_sdk.add_breadcrumb(
        category=category, message=message, level=level, data=data
    )


def celery_base_data_hook(request: AuthenticatedHttpRequest, data) -> None:
    data["framework"] = "celery"


def init_sentry() -> None:
    sentry_sdk = get_sentry_sdk()
    from sentry_sdk.integrations.celery import CeleryIntegration  # noqa: PLC0415
    from sentry_sdk.integrations.django import DjangoIntegration  # noqa: PLC0415
    from sentry_sdk.integrations.logging import ignore_logger  # noqa: PLC0415
    from sentry_sdk.integrations.redis import RedisIntegration  # noqa: PLC0415

    integrations = [
        CeleryIntegration(monitor_beat_tasks=settings.SENTRY_MONITOR_BEAT_TASKS),
        DjangoIntegration(),
        RedisIntegration(),
    ]

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=integrations,
        auto_enabling_integrations=False,
        send_default_pii=settings.SENTRY_SEND_PII,
        release=weblate.utils.version.GIT_REVISION or weblate.utils.version.TAG_NAME,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
        in_app_include=[
            "weblate",
            "wlhosted",
            "wllegal",
            "weblate_fedora_messaging",
            "weblate_language_data",
            "translate",
            "translation_finder",
        ],
        attach_stacktrace=True,
        _experiments={"max_spans": 2000},
        keep_alive=True,
        **settings.SENTRY_EXTRA_ARGS,
    )
    # Ignore Weblate logging, those should trigger proper errors
    ignore_logger("weblate")
    ignore_logger("weblate.*")
    # Python Social Auth logs provider failures before Weblate classifies them.
    ignore_logger("social")
    ignore_logger("social.*")


def init_google_cloud_error_reporting() -> None:
    google_error_reporting = get_google_cloud_error_reporting()
    if settings.GOOGLE_CLOUD_ERROR_REPORTING is None:
        return
    config = dict(cast("dict[str, object]", settings.GOOGLE_CLOUD_ERROR_REPORTING))
    config.setdefault("service", "weblate")
    config.setdefault(
        "version", weblate.utils.version.GIT_REVISION or weblate.utils.version.TAG_NAME
    )
    _STATE["google_cloud_error_reporting_client"] = google_error_reporting.Client(
        **config
    )
    LOGGER.info("configured Google Cloud Error Reporting")


def _init_opentelemetry_after_fork() -> None:
    """Reinitialize OpenTelemetry tracing in forked child processes."""
    _STATE["opentelemetry_initialized_pid"] = None
    _STATE["opentelemetry_provider"] = None
    init_opentelemetry()


def _register_opentelemetry_after_fork() -> None:
    if _STATE["opentelemetry_at_fork_registered"] or not hasattr(
        os, "register_at_fork"
    ):
        return
    os.register_at_fork(after_in_child=_init_opentelemetry_after_fork)
    _STATE["opentelemetry_at_fork_registered"] = True


def init_opentelemetry() -> None:
    """Initialize OpenTelemetry tracing."""
    from weblate.utils.tracing import configure_opentelemetry_tracer  # noqa: PLC0415

    current_pid = os.getpid()
    if _STATE["opentelemetry_initialized_pid"] == current_pid:
        return
    if (
        not settings.OPENTELEMETRY_ENABLED
        or not settings.OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT
    ):
        configure_opentelemetry_tracer(None)
        return

    sample_rate = settings.OPENTELEMETRY_TRACES_SAMPLE_RATE
    if sample_rate < 0 or sample_rate > 1:
        msg = "OPENTELEMETRY_TRACES_SAMPLE_RATE has to be between 0 and 1"
        raise ImproperlyConfigured(msg)
    if sample_rate == 0:
        configure_opentelemetry_tracer(None)
        return

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.celery import (  # noqa: PLC0415
        CeleryInstrumentor,
    )
    from opentelemetry.instrumentation.django import (  # noqa: PLC0415
        DjangoInstrumentor,
    )
    from opentelemetry.instrumentation.psycopg import (  # noqa: PLC0415
        PsycopgInstrumentor,
    )
    from opentelemetry.instrumentation.redis import RedisInstrumentor  # noqa: PLC0415
    from opentelemetry.instrumentation.requests import (  # noqa: PLC0415
        RequestsInstrumentor,
    )
    from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
    from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased  # noqa: PLC0415

    previous_provider = _STATE["opentelemetry_provider"]
    if previous_provider is not None:
        with suppress(Exception):
            previous_provider.shutdown()

    resource_attributes = {
        "service.name": settings.OPENTELEMETRY_SERVICE_NAME,
        "service.version": weblate.utils.version.VERSION,
    }
    if settings.SENTRY_ENVIRONMENT:
        resource_attributes["deployment.environment"] = settings.SENTRY_ENVIRONMENT
    resource_attributes.update(settings.OPENTELEMETRY_EXTRA_RESOURCE_ATTRIBUTES)

    provider = TracerProvider(
        resource=Resource.create(resource_attributes),
        sampler=TraceIdRatioBased(sample_rate),
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=settings.OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT,
                headers=settings.OPENTELEMETRY_EXPORTER_OTLP_HEADERS,
            )
        )
    )
    configure_opentelemetry_tracer(
        provider.get_tracer("weblate", weblate.utils.version.VERSION)
    )

    for instrumentor_class in (
        DjangoInstrumentor,
        CeleryInstrumentor,
        RedisInstrumentor,
        RequestsInstrumentor,
        PsycopgInstrumentor,
    ):
        instrumentor = instrumentor_class()
        if instrumentor.is_instrumented_by_opentelemetry:
            instrumentor.uninstrument()
        instrumentor.instrument(tracer_provider=provider)

    _STATE["opentelemetry_initialized_pid"] = current_pid
    _STATE["opentelemetry_provider"] = provider
    _register_opentelemetry_after_fork()
    LOGGER.info("configured OpenTelemetry tracing")


def init_rollbar() -> None:
    rollbar = get_rollbar()
    rollbar.init(**settings.ROLLBAR)  # type: ignore[misc]
    rollbar.BASE_DATA_HOOK = celery_base_data_hook
    LOGGER.info("configured Rollbar error collection")


def init_error_collection(celery=False) -> None:
    if settings.SENTRY_DSN:
        init_sentry()

    if settings.GOOGLE_CLOUD_ERROR_REPORTING is not None:
        init_google_cloud_error_reporting()

    init_opentelemetry()

    if celery and hasattr(settings, "ROLLBAR"):
        init_rollbar()
