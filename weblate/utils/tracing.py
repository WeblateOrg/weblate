# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from contextlib import ExitStack, contextmanager
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, cast

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from collections.abc import Generator

    from opentelemetry.trace import Tracer


class AttributeSpan(Protocol):
    def set_attribute(self, key: str, value: bool | float | str) -> None: ...


class ErrorSpan(AttributeSpan, Protocol):
    def add_event(
        self, name: str, attributes: dict[str, bool | float | str] | None = None
    ) -> None: ...

    def is_recording(self) -> bool: ...

    def record_exception(
        self,
        exception: BaseException,
        attributes: dict[str, bool | float | str] | None = None,
    ) -> None: ...

    def set_status(self, status: object) -> None: ...


_STATE: dict[str, object | None] = {"opentelemetry_tracer": None}
LOGGER = logging.getLogger("weblate.tracing")


def get_sentry_sdk():
    try:
        return import_module("sentry_sdk")
    except ImportError as error:
        msg = "sentry-sdk has to be installed to use SENTRY_DSN"
        raise ImproperlyConfigured(msg) from error


def configure_opentelemetry_tracer(tracer: Tracer | None) -> None:
    """Configure OpenTelemetry tracer used for custom Weblate spans."""
    _STATE["opentelemetry_tracer"] = tracer


def _set_opentelemetry_attribute(span: AttributeSpan, name: str, value: object) -> None:
    if value is None:
        return
    if isinstance(value, bool | int | float | str):
        span.set_attribute(name, value)
        return
    span.set_attribute(name, str(value))


def _build_error_attributes(
    cause: str, level: str, attributes: dict[str, object | None] | None
) -> dict[str, bool | float | str]:
    result: dict[str, bool | float | str] = {
        "weblate.error.cause": cause,
        "weblate.error.level": level,
    }
    if attributes:
        for name, value in attributes.items():
            if value is None:
                continue
            if isinstance(value, bool | int | float | str):
                result[name] = value
                continue
            result[name] = str(value)
    return result


def _record_error_on_span(
    span: ErrorSpan,
    cause: str,
    level: str,
    exception: BaseException | None,
    attributes: dict[str, bool | float | str],
) -> None:
    if exception is not None:
        span.record_exception(exception, attributes=attributes)
    else:
        span.add_event("weblate.error", attributes=attributes)

    if level in {"critical", "error", "fatal"}:
        # ruff: ignore[import-outside-top-level]
        from opentelemetry.trace import Status, StatusCode

        span.set_status(Status(StatusCode.ERROR, description=cause))


def record_error(
    cause: str,
    *,
    level: str,
    exception: BaseException | None = None,
    attributes: dict[str, object | None] | None = None,
) -> None:
    """Record a handled error in OpenTelemetry tracing."""
    try:
        _record_error(cause, level=level, exception=exception, attributes=attributes)
    except Exception:
        LOGGER.exception("Could not record OpenTelemetry error")


def _record_error(
    cause: str,
    *,
    level: str,
    exception: BaseException | None = None,
    attributes: dict[str, object | None] | None = None,
) -> None:
    """Record a handled error in OpenTelemetry tracing."""
    tracer = cast("Tracer | None", _STATE["opentelemetry_tracer"])
    if tracer is None:
        return

    # ruff: ignore[import-outside-top-level]
    from opentelemetry import trace

    error_attributes = _build_error_attributes(cause, level, attributes)
    span = cast("ErrorSpan", trace.get_current_span())
    if span.is_recording():
        _record_error_on_span(span, cause, level, exception, error_attributes)
        return

    with tracer.start_as_current_span("weblate.report_error") as report_span:
        _record_error_on_span(
            cast("ErrorSpan", report_span), cause, level, exception, error_attributes
        )


@contextmanager
def start_span(
    op: str, name: str | None = None, **attributes: object
) -> Generator[None]:
    """Start tracing span in all configured tracing backends."""
    with ExitStack() as stack:
        if getattr(settings, "SENTRY_DSN", None):
            sentry_sdk = get_sentry_sdk()
            stack.enter_context(sentry_sdk.start_span(op=op, name=name))

        tracer = cast("Tracer | None", _STATE["opentelemetry_tracer"])
        if tracer is not None:
            span = stack.enter_context(tracer.start_as_current_span(op))
            _set_opentelemetry_attribute(span, "weblate.operation", op)
            _set_opentelemetry_attribute(span, "weblate.name", name)
            for attribute_name, value in attributes.items():
                _set_opentelemetry_attribute(span, attribute_name, value)

        yield
