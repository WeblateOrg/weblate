# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
import os
import re
import sys
from contextlib import suppress
from copy import deepcopy
from importlib import import_module
from json import JSONDecodeError
from traceback import format_exception
from typing import TYPE_CHECKING, Any, Literal, cast
from urllib.parse import unquote_plus

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import get_language

import weblate.utils.version
from weblate.utils.tracing import record_error

if TYPE_CHECKING:
    from collections.abc import Callable

    from sentry_sdk.types import DataCollectionUserOptions, Event, Hint, SpanJSON

    from weblate.auth.models import AuthenticatedHttpRequest

ERROR_LOGGER = "weblate.errors"
SENTRY_SECRET_DENYLIST = (
    # Keep the SDK 2 event scrubber's credential coverage on serialized data.
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "auth",
    "credentials",
    "mysql_pwd",
    "privatekey",
    "private_key",
    "token",
    "session",
    "csrftoken",
    "sessionid",
    "x_csrftoken",
    "cookie",
    "authorization",
    "proxy-authorization",
    "x_api_key",
    "aiohttp_session",
    "connect.sid",
    "csrf_token",
    "csrf",
    "_csrf",
    "_csrf_token",
    "phpsessid",
    "_session",
    "symfony",
    "user_session",
    "_xsrf",
    "xsrf-token",
    "passphrase",
    "borg_passphrase",
    "borg_new_passphrase",
    "set-cookie",
    # Machine translation configuration and provider authentication headers.
    "key",
    "api-key",
    "x-api-key",
    "x-goog-api-key",
    "mmt-apikey",
    "ocp-apim-subscription-key",
    # GitHub App authentication and OAuth responses.
    "private_key_pem",
    "pem",
    "client_secret",
    "webhook_secret",
    "access_token",
    "refresh_token",
    "cached_token",
    "user_token",
)
SENTRY_PII_DENYLIST = ("x_forwarded_for", "x_real_ip", "ip_address", "remote_addr")
SENTRY_TOKEN_PATH = re.compile(
    r"(/(?:accounts/invitation|hooks/integrations|machinery/etranslation/callback)/)"
    r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}(?=/|[?#\s]|$)",
    re.IGNORECASE,
)

SENTRY_QUERY_PARAMETER = re.compile(
    r"(?<![\w%+.-])(?P<name>[\w%+.-]+)=(?P<value>[^&\s#'\"<>]*)"
)
SENTRY_URL_USERINFO = re.compile(
    r"(?<![a-z0-9+.-])(?P<scheme>[a-z][a-z0-9+.-]*://)[^/\s?#\"<>]*@",
    re.IGNORECASE,
)
SENTRY_ROUTINE_TRACE_PATHS = frozenset({"/-/pow/verify/", "/js/i18n/", "/js/flags/"})
SENTRY_WIDGET_IMAGE_PATH = re.compile(
    r"/(?:widget/(?:[^/]+/)+|widgets/(?:[^/]+/){2,3})[^/-]+-[^/-]+\.(?:png|svg)"
)
SENTRY_AVATAR_PATH = re.compile(r"/avatar/[0-9]+/[^/]+\.png")

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
    exception: BaseException | None = None,
) -> None:
    """Report an active or explicitly supplied exception."""
    # pylint: disable-next=unused-variable
    __traceback_hide__ = True
    error = exception if exception is not None else sys.exc_info()[1]
    if error is None:
        msg = f"report_error called without an exception: {cause}"
        raise RuntimeError(msg)
    locale = get_language()

    if not skip_error_reporting:
        if hasattr(settings, "ROLLBAR"):
            rollbar = get_rollbar()
            rollbar.report_exc_info(
                (type(error), error, error.__traceback__), level=level
            )

        if getattr(settings, "SENTRY_DSN", None):
            sentry_sdk = get_sentry_sdk()
            sentry_sdk.set_tag("cause", cause)
            if project is not None:
                sentry_sdk.set_tag("project", project.slug)
            sentry_sdk.set_tag("user.locale", locale)
            sentry_sdk.set_level(level)
            sentry_sdk.capture_exception(error)

        google_client = _STATE["google_cloud_error_reporting_client"]
        if google_client is not None:
            google_client.report(
                "".join(format_exception(type(error), error, error.__traceback__))
            )

        record_error(
            cause,
            level=level,
            exception=error,
            attributes={
                "weblate.project": None if project is None else project.slug,
                "weblate.user_locale": locale,
            },
        )

    _log_error(
        cause,
        level=level,
        extra_log=extra_log,
        print_tb=print_tb,
        exception=error,
    )


def report_message(
    cause: str,
    *,
    level: Literal[
        "fatal", "critical", "error", "warning", "info", "debug"
    ] = "warning",
    skip_error_reporting: bool = False,
    extra_log: str | None = None,
    project=None,
) -> None:
    """Report a message without using an ambient exception."""
    locale = get_language()

    if not skip_error_reporting:
        if hasattr(settings, "ROLLBAR"):
            get_rollbar().report_message(cause, level=level)

        if settings.SENTRY_DSN:
            sentry_sdk = get_sentry_sdk()
            sentry_sdk.set_tag("cause", cause)
            if project is not None:
                sentry_sdk.set_tag("project", project.slug)
            sentry_sdk.set_tag("user.locale", locale)
            sentry_sdk.set_level(level)
            sentry_sdk.capture_message(cause)

        google_client = _STATE["google_cloud_error_reporting_client"]
        if google_client is not None:
            google_client.report(cause)

        record_error(
            cause,
            level=level,
            exception=None,
            attributes={
                "weblate.project": None if project is None else project.slug,
                "weblate.user_locale": locale,
            },
        )

    log = getattr(LOGGER, level)
    if extra_log:
        log("%s: %s", cause, extra_log)
    else:
        log("%s", cause)


def _log_error(
    cause: str,
    *,
    level: Literal[
        "fatal", "critical", "error", "warning", "info", "debug"
    ] = "warning",
    extra_log: str | None = None,
    print_tb: bool = False,
    exception: BaseException | None = None,
) -> None:
    """Log the current exception without reporting it to external services."""
    log = getattr(LOGGER, level)
    error = exception

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
    if print_tb and error is not None:
        LOGGER.error(
            cause,
            exc_info=(type(error), error, error.__traceback__),
        )


def log_handled_exception(
    cause: str,
    *,
    level: Literal[
        "fatal", "critical", "error", "warning", "info", "debug"
    ] = "warning",
    extra_log: str | None = None,
) -> None:
    """Log a handled exception without reporting it to Sentry or Rollbar."""
    _log_error(
        cause,
        level=level,
        extra_log=extra_log,
        exception=sys.exc_info()[1],
    )


class SentryRedactor:
    """Filter credentials from serialized Sentry data."""

    def __init__(self, *, send_pii: bool = False) -> None:
        terms = (
            SENTRY_SECRET_DENYLIST
            if send_pii
            else (
                *SENTRY_SECRET_DENYLIST,
                *SENTRY_PII_DENYLIST,
            )
        )
        self.secret_fields = frozenset(term.replace("-", "_") for term in terms)
        secret_names = "|".join(
            re.escape(name).replace("_", "[-_]")
            for name in sorted(self.secret_fields, key=len, reverse=True)
        )
        # SDK frames can contain header tuple/dict reprs and raw HTTP bytes.
        self.quoted_secret = re.compile(
            rf"(?P<prefix>(?P<quote>['\"])(?:HTTP_)?(?:{secret_names})(?P=quote)"
            r"\s*[:,]\s*b?(?P<value_quote>['\"]))"
            r"(?:\\[\s\S]|(?!(?P=value_quote))[^\\])*"
            r"(?P<suffix>(?P=value_quote)|\\?$)",
            re.IGNORECASE,
        )
        self.header_secret = re.compile(
            rf"(?P<prefix>(?:(?<![\w-])|(?<=\\[rn]))(?:{secret_names})[ \t]*:[ \t]*)"
            r"(?:(?!\\[rn])[^\r\n])*",
            re.IGNORECASE,
        )

    def is_secret(self, name: str) -> bool:
        return (
            name.lower().replace("-", "_").removeprefix("http_") in self.secret_fields
        )

    def _scrub_query_parameter(self, match: re.Match[str]) -> str:
        name = match["name"]
        if self.is_secret(unquote_plus(name)):
            return f"{name}=[Filtered]"
        return match[0]

    def scrub(self, value: object) -> object:
        if isinstance(value, dict):
            for key, item in value.items():
                value[key] = (
                    "[Filtered]"
                    if isinstance(key, str) and self.is_secret(key)
                    else self.scrub(item)
                )
        elif isinstance(value, (list, tuple)):
            items = [self.scrub(item) for item in value]
            # Header pairs can be added by callbacks after SDK serialization.
            if (
                len(value) == 2
                and isinstance(value[0], str)
                and self.is_secret(value[0])
            ):
                items[1] = "[Filtered]"
            if isinstance(value, tuple):
                return tuple(items)
            value[:] = items
        elif isinstance(value, str):
            value = self.quoted_secret.sub(r"\g<prefix>[Filtered]\g<suffix>", value)
            if ":" in value:
                value = self.header_secret.sub(r"\g<prefix>[Filtered]", value)
            if "://" in value:
                value = SENTRY_URL_USERINFO.sub(r"\g<scheme>[Filtered]@", value)
            if "/" in value:
                value = SENTRY_TOKEN_PATH.sub(r"\g<1>[Filtered]", value)
            if "=" in value:
                value = SENTRY_QUERY_PARAMETER.sub(self._scrub_query_parameter, value)
        return value

    def scrub_span(self, span: SpanJSON) -> SpanJSON:
        span["name"] = cast("str", self.scrub(span["name"]))
        if (attributes := span.get("attributes")) is not None:
            attributes.pop("process.command_args", None)
            for key, value in attributes.items():
                if key.startswith(("http.request.header.", "http.response.header.")):
                    header = key.split(".", 3)[-1]
                    if self.is_secret(header):
                        attributes[key] = (
                            ["[Filtered]"] if isinstance(value, list) else "[Filtered]"
                        )
            self.scrub(attributes)
        return span


class SentryBeforeSend:
    """Scrub serialized events and bound the size of long exception chains."""

    def __init__(
        self,
        callback: Callable[[Event, Hint], Event | None] | None = None,
        *,
        redactor: SentryRedactor | None = None,
    ) -> None:
        self.callback = callback
        self.redactor = redactor if redactor is not None else SentryRedactor()

    def __call__(self, event: Event, hint: Hint) -> Event | None:
        # ruff: ignore[import-outside-top-level]
        from sentry_sdk.utils import json_dumps

        if self.callback is not None:
            filtered_event = self.callback(event, hint)
            if filtered_event is None:
                return None
            event = filtered_event
        self.redactor.scrub(event)
        if len(json_dumps(event)) <= 1_000_000:
            return event

        values = event.get("exception", {}).get("values", [])
        # Exception groups have a hierarchy rather than a linear cause chain.
        if any(
            value.get("mechanism", {}).get("is_exception_group") for value in values
        ):
            return event
        original_count = len(values)
        while len(values) > 2 and len(json_dumps(event)) > 900_000:
            # Preserve the original cause and the final exception. Remove
            # intermediate exceptions in batches, leaving room for metadata.
            values = values[:1] + values[1 + max(1, (len(values) - 2) // 2) :]
            # SDK 3 also assigns parent IDs to ordinary exception chains.
            if (mechanism := values[0].get("mechanism")) and (
                parent_id := values[1].get("mechanism", {}).get("exception_id")
            ) is not None:
                mechanism["parent_id"] = parent_id
            event["exception"]["values"] = values
            # Serialized annotations refer to indices in the original chain.
            metadata = event.get("_meta")
            if isinstance(metadata, dict):
                metadata.pop("exception", None)
            event.setdefault("contexts", {})["weblate_exception_chain"] = {
                "original_count": original_count,
                "omitted_count": original_count - len(values),
            }

        return event


class SentryBeforeSendSpan:
    def __init__(
        self,
        redactor: SentryRedactor,
        callback: Callable[[SpanJSON, Hint], SpanJSON | None] | None = None,
    ) -> None:
        self.redactor = redactor
        self.callback = callback

    def __call__(self, span: SpanJSON, hint: Hint) -> SpanJSON:
        if self.callback is not None:
            # Preserve the original if the callback mutates the span and then fails.
            try:
                replacement = self.callback(deepcopy(span), hint)
                if replacement is not None and isinstance(replacement.get("name"), str):
                    return self.redactor.scrub_span(replacement)
            except Exception:
                # The SDK would otherwise send the original without redaction.
                LOGGER.warning("Sentry span callback failed")
        return self.redactor.scrub_span(span)


def sentry_data_collection(*, send_pii: bool) -> DataCollectionUserOptions:
    terms = list(SENTRY_SECRET_DENYLIST)
    if not send_pii:
        terms.extend(
            (*SENTRY_PII_DENYLIST, "forwarded", "-ip", "remote-", "via", "-user")
        )
    return {
        "user_info": send_pii,
        "http_bodies": ["incoming_request"] if send_pii else [],
        "http_headers": {"request": {"mode": "denylist", "terms": terms}},
        "cookies": {"mode": "denylist", "terms": terms}
        if send_pii
        else {"mode": "off"},
        "url_query_params": {"mode": "denylist", "terms": terms},
        "stack_frame_variables": {"mode": "denylist", "terms": terms},
        "database_query_data": False,
        "queues": False,
        "graphql": {"document": False, "variables": False},
        "gen_ai": {"inputs": False, "outputs": False},
        "mcp": {"inputs": False, "outputs": False},
    }


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


def sample_sentry_traces(sampling_context: dict[str, Any]) -> float | bool:
    """Sample routine requests and standalone statistics tasks at reduced rates."""
    parent_sampled = sampling_context.get("parent_sampled")
    if isinstance(parent_sampled, bool):
        return parent_sampled

    sample_rate = settings.SENTRY_TRACES_SAMPLE_RATE
    celery_job = sampling_context.get("celery_job", {})
    if celery_job.get("task") == "weblate.utils.tasks.update_translation_stats_parents":
        return sample_rate * 0.25

    wsgi_environ = sampling_context.get("wsgi_environ", {})
    asgi_scope = sampling_context.get("asgi_scope", {})
    path = wsgi_environ.get("PATH_INFO", "")
    if asgi_scope.get("type") == "http":
        path = asgi_scope.get("path", "")
        root_path = settings.FORCE_SCRIPT_NAME or asgi_scope.get("root_path") or ""
        root_path = root_path.rstrip("/")
        if root_path and path.startswith(f"{root_path}/"):
            path = path[len(root_path) :]

    url_prefix = settings.URL_PREFIX.strip("/")
    if url_prefix:
        prefix = f"/{url_prefix}"
        if not path.startswith(f"{prefix}/"):
            return sample_rate
        path = path[len(prefix) :]

    if (
        path in SENTRY_ROUTINE_TRACE_PATHS
        or SENTRY_WIDGET_IMAGE_PATH.fullmatch(path)
        or SENTRY_AVATAR_PATH.fullmatch(path)
    ):
        return sample_rate * 0.1
    return sample_rate


def init_sentry() -> None:
    sentry_sdk = get_sentry_sdk()
    # ruff: ignore[import-outside-top-level]
    from sentry_sdk.integrations.celery import (
        CeleryIntegration,
    )

    # ruff: ignore[import-outside-top-level]
    from sentry_sdk.integrations.django import (
        DjangoIntegration,
    )

    # ruff: ignore[import-outside-top-level]
    from sentry_sdk.integrations.httpx2 import (
        Httpx2Integration,
    )

    # ruff: ignore[import-outside-top-level]
    from sentry_sdk.integrations.logging import (
        LoggingIntegration,
        ignore_logger_for_events,
    )

    # ruff: ignore[import-outside-top-level]
    from sentry_sdk.integrations.redis import (
        RedisIntegration,
    )

    integrations = [
        CeleryIntegration(monitor_beat_tasks=settings.SENTRY_MONITOR_BEAT_TASKS),
        DjangoIntegration(cache_spans=False),
        Httpx2Integration(),
        RedisIntegration(),
        LoggingIntegration(
            level=None, event_level=logging.ERROR, breadcrumb_level=logging.INFO
        ),
    ]
    sentry_extra_args = dict(settings.SENTRY_EXTRA_ARGS)
    for option, replacement in (
        ("event_scrubber", "data_collection or before_send"),
        (
            "before_send_transaction",
            "before_send_span, ignore_spans, or traces_sampler",
        ),
    ):
        if option in sentry_extra_args:
            msg = f"Sentry SDK 3 removed {option} from SENTRY_EXTRA_ARGS. Use {replacement}."
            raise ImproperlyConfigured(msg)

    traces_sample_rate = settings.SENTRY_TRACES_SAMPLE_RATE
    if traces_sample_rate:
        sentry_extra_args.setdefault("traces_sampler", sample_sentry_traces)
    sentry_extra_args.setdefault(
        "profile_session_sample_rate", settings.SENTRY_PROFILES_SAMPLE_RATE
    )
    sentry_extra_args.setdefault("profile_lifecycle", "trace")
    data_collection = sentry_data_collection(send_pii=settings.SENTRY_SEND_PII)
    data_collection.update(sentry_extra_args.pop("data_collection", {}))
    redactor = SentryRedactor(send_pii=settings.SENTRY_SEND_PII)
    before_send = sentry_extra_args.pop("before_send", None)
    before_send_check_in = sentry_extra_args.pop("before_send_check_in", before_send)
    before_send_span = sentry_extra_args.pop("before_send_span", None)

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=integrations,
        auto_enabling_integrations=False,
        data_collection=data_collection,
        before_send=SentryBeforeSend(before_send, redactor=redactor),
        before_send_check_in=SentryBeforeSend(before_send_check_in, redactor=redactor),
        before_send_span=SentryBeforeSendSpan(redactor, before_send_span),
        release=weblate.utils.version.GIT_REVISION or weblate.utils.version.TAG_NAME,
        environment=settings.SENTRY_ENVIRONMENT,
        traces_sample_rate=traces_sample_rate,
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
        keep_alive=True,
        **sentry_extra_args,
    )
    # Ignore Weblate logging, those should trigger proper errors
    ignore_logger_for_events("weblate")
    ignore_logger_for_events("weblate.*")
    # Python Social Auth logs provider failures before Weblate classifies them.
    ignore_logger_for_events("social")
    ignore_logger_for_events("social.*")


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


def validate_opentelemetry_settings() -> None:
    """Validate OpenTelemetry settings which can fail application startup."""
    if (
        not settings.OPENTELEMETRY_ENABLED
        or not settings.OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT
    ):
        return
    sample_rate = settings.OPENTELEMETRY_TRACES_SAMPLE_RATE
    if sample_rate < 0 or sample_rate > 1:
        msg = "OPENTELEMETRY_TRACES_SAMPLE_RATE has to be between 0 and 1"
        raise ImproperlyConfigured(msg)


def init_opentelemetry() -> None:
    """Initialize OpenTelemetry tracing."""
    # ruff: ignore[import-outside-top-level]
    from weblate.utils.tracing import (
        configure_opentelemetry_tracer,
    )

    current_pid = os.getpid()
    if _STATE["opentelemetry_initialized_pid"] == current_pid:
        return
    if (
        not settings.OPENTELEMETRY_ENABLED
        or not settings.OPENTELEMETRY_EXPORTER_OTLP_ENDPOINT
    ):
        configure_opentelemetry_tracer(None)
        return

    validate_opentelemetry_settings()
    sample_rate = settings.OPENTELEMETRY_TRACES_SAMPLE_RATE
    if sample_rate == 0:
        configure_opentelemetry_tracer(None)
        return

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # ruff: ignore[import-outside-top-level]
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.celery import (  # ruff: ignore[import-outside-top-level]
        CeleryInstrumentor,
    )
    from opentelemetry.instrumentation.django import (  # ruff: ignore[import-outside-top-level]
        DjangoInstrumentor,
    )
    from opentelemetry.instrumentation.psycopg import (  # ruff: ignore[import-outside-top-level]
        PsycopgInstrumentor,
    )

    # ruff: ignore[import-outside-top-level]
    from opentelemetry.instrumentation.redis import (
        RedisInstrumentor,
    )
    from opentelemetry.instrumentation.requests import (  # ruff: ignore[import-outside-top-level]
        RequestsInstrumentor,
    )

    # ruff: ignore[import-outside-top-level]
    from opentelemetry.sdk.resources import (
        Resource,
    )

    # ruff: ignore[import-outside-top-level]
    from opentelemetry.sdk.trace import (
        TracerProvider,
    )

    # ruff: ignore[import-outside-top-level]
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
    )

    # ruff: ignore[import-outside-top-level]
    from opentelemetry.sdk.trace.sampling import (
        TraceIdRatioBased,
    )

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


def validate_error_collection_settings() -> None:
    """Validate configured error collection backends before serving requests."""
    if settings.SENTRY_DSN:
        get_sentry_sdk()

    if settings.GOOGLE_CLOUD_ERROR_REPORTING is not None:
        get_google_cloud_error_reporting()

    validate_opentelemetry_settings()

    if hasattr(settings, "ROLLBAR"):
        get_rollbar()


def init_error_collection(celery=False) -> None:
    validate_error_collection_settings()

    if settings.SENTRY_DSN:
        init_sentry()

    if settings.GOOGLE_CLOUD_ERROR_REPORTING is not None:
        init_google_cloud_error_reporting()

    init_opentelemetry()

    if celery and hasattr(settings, "ROLLBAR"):
        init_rollbar()
