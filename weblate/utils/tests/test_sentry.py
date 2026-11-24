# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import logging
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from asyncio import run
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, patch

import django
import pytest
import sentry_sdk
from asgiref.testing import ApplicationCommunicator
from celery import Celery
from celery.beat import ScheduleEntry, Scheduler
from celery.schedules import crontab
from django.conf import settings
from django.core.asgi import get_asgi_application
from django.core.wsgi import get_wsgi_application
from django.http import HttpResponse
from django.test import AsyncRequestFactory, RequestFactory
from django.urls import path

from weblate.utils.tracing import start_span

if TYPE_CHECKING:
    from django.http import HttpRequest
    from sentry_sdk.envelope import Envelope
    from sentry_sdk.types import Event, Hint, SamplingContext, SpanJSON

ROUTINE_TASK = "weblate.utils.tasks.update_translation_stats_parents"
INVITATION_TOKEN = "39770f75-11da-46ae-b332-577d7b6d80b4"
FORM_SECRET = "form-secret"
AUTHORIZATION_SECRET = "authorization-secret"
CLIENT_IP = "192.0.2.25"
SAMPLED = "321e44018032499a86acfa0f4525ff33-0123456789abcdef-1"
UNSAMPLED = "821e44018032499a86acfa0f4525ff33-0123456789abcdef-0"
LOGGER = logging.getLogger("sentry-startup-test")


def request_view(request: HttpRequest, **_kwargs: object) -> HttpResponse:
    with start_span("test.operation", "custom child span"):
        if request.method == "POST":
            request.POST.get("diagnostic")
            LOGGER.info("useful breadcrumb")
            logging.getLogger("weblate.test").error("excluded Weblate logger")
            logging.getLogger("social.test").error("excluded Social Auth logger")
            LOGGER.error("handled request error")
    return HttpResponse("ok")


urlpatterns = [
    path("accounts/invitation/<uuid:token>/", request_view),
    path("js/flags/", request_view),
]


@pytest.mark.parametrize("mode", ["disabled", "private", "pii", "unprofiled"])
def test_sentry_startup(mode: str) -> None:
    # Django and Sentry both install process-wide integration state.
    result = subprocess.run(
        [sys.executable, "-m", "weblate.utils.tests.test_sentry", mode],
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "weblate.settings_test"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def run_wsgi_request(route: str, *, trace: str = "", post: bool = False) -> None:
    factory = RequestFactory()
    if post:
        request = factory.post(
            route, {"diagnostic": "incoming-form-value", "password": FORM_SECRET}
        )
    else:
        request = factory.get(route)
    request.META.update(
        HTTP_HOST="example.com",
        HTTP_AUTHORIZATION=f"Bearer {AUTHORIZATION_SECRET}",
        HTTP_X_FORWARDED_FOR=CLIENT_IP,
    )
    if trace:
        request.META["HTTP_SENTRY_TRACE"] = trace
    start_response = Mock()
    response = get_wsgi_application()(request.META, start_response)
    try:
        assert b"".join(response) == b"ok"
    finally:
        response.close()
    start_response.assert_called_once()
    assert start_response.call_args.args[0] == "200 OK"


async def run_asgi_request() -> None:
    scope = AsyncRequestFactory().get("/js/flags/").scope
    communicator = ApplicationCommunicator(get_asgi_application(), scope)
    await communicator.send_input({"type": "http.request", "body": b""})
    assert (await communicator.receive_output(timeout=5))["status"] == 200
    assert (await communicator.receive_output(timeout=5))["body"] == b"ok"
    await communicator.wait(timeout=5)


def run_celery_task() -> None:
    app = Celery("sentry-startup-test", broker="memory://", set_as_current=False)
    app.conf.task_always_eager = True

    task = app.tasks[ROUTINE_TASK]
    with patch.object(task, "run", lambda _pk: None):
        assert task.apply(args=(1,), throw=True).successful()
        scheduler = Scheduler(app=app, lazy=True)
        entry = ScheduleEntry(
            name="sentry-test-beat",
            task=ROUTINE_TASK,
            schedule=crontab(),
            args=(1,),
            app=app,
        )
        scheduler.apply_entry(entry)


def check_startup(mode: str) -> None:
    rates: dict[str, float | bool] = {}

    def capture_sampling(context: SamplingContext) -> float | bool:
        # ruff: ignore[import-outside-top-level]
        from weblate.utils.errors import sample_sentry_traces

        rate = sample_sentry_traces(context)
        for integration in ("wsgi_environ", "asgi_scope", "celery_job"):
            if integration in context and context.get("parent_sampled") is None:
                rates.setdefault(integration, rate)
        return rate

    def before_send(event: Event, _hint: Hint) -> Event:
        event.setdefault("extra", {})["client-secret"] = "callback-error-secret"
        return event

    def before_send_span(span: SpanJSON, _hint: Hint) -> SpanJSON:
        span.setdefault("attributes", {})["http.request.header.set-cookie"] = [
            "callback-span-secret"
        ]
        return span

    settings.ROOT_URLCONF = __name__
    settings.MIDDLEWARE = []
    settings.ALLOWED_HOSTS = ["example.com", "testserver"]
    settings.SENTRY_DSN = None if mode == "disabled" else "https://public@example.com/1"
    settings.SENTRY_TRACES_SAMPLE_RATE = 1.0
    settings.SENTRY_PROFILES_SAMPLE_RATE = 0.0 if mode == "unprofiled" else 1.0
    settings.SENTRY_SEND_PII = mode == "pii"
    settings.SENTRY_EXTRA_ARGS = {
        "traces_sampler": capture_sampling,
        "before_send": before_send,
        "before_send_span": before_send_span,
    }
    envelopes: list[Envelope] = []
    LOGGER.setLevel(logging.INFO)
    with patch.object(
        sentry_sdk.HttpTransport,
        "capture_envelope",
        autospec=True,
        side_effect=lambda _transport, envelope: envelopes.append(envelope),
    ):
        django.setup()
        if mode == "disabled":
            assert not sentry_sdk.is_initialized()
            return
        assert sentry_sdk.is_initialized()
        client = sentry_sdk.get_client()
        try:
            run_wsgi_request("/js/flags/", trace=UNSAMPLED)
            sentry_sdk.flush()
            assert not any(
                item.type in {"span", "profile_chunk"}
                for envelope in envelopes
                for item in envelope.items
            )
            run_wsgi_request(
                f"/accounts/invitation/{INVITATION_TOKEN}/", trace=SAMPLED, post=True
            )
            run_wsgi_request("/js/flags/")
            run(run_asgi_request())
            run_celery_task()
            sentry_sdk.flush()
        finally:
            client.close()

    assert rates == {"wsgi_environ": 0.1, "asgi_scope": 0.1, "celery_job": 0.25}
    span_data = b"".join(
        item.get_bytes()
        for envelope in envelopes
        for item in envelope.items
        if item.type == "span"
    )
    assert b"custom child span" in span_data
    assert b"test.operation" in span_data
    assert (b"sentry.profiler_id" in span_data) is (mode != "unprofiled")
    check_ins = [
        json.loads(item.get_bytes())
        for envelope in envelopes
        for item in envelope.items
        if item.type == "check_in"
    ]
    assert {item["monitor_slug"] for item in check_ins} == {"sentry-test-beat"}
    assert {item["status"] for item in check_ins} == {"in_progress", "ok"}
    assert len({item["check_in_id"] for item in check_ins}) == 1
    assert not any(item.type == "log" for env in envelopes for item in env.items)
    reports = [event for env in envelopes if (event := env.get_event()) is not None]
    assert len(reports) == 1
    assert "handled request error" in str(reports)
    breadcrumbs = cast("dict[str, list[dict[str, str]]]", reports[0]["breadcrumbs"])[
        "values"
    ]
    breadcrumb_messages = {crumb.get("message") for crumb in breadcrumbs}
    assert "useful breadcrumb" in breadcrumb_messages
    assert (
        not {"excluded Weblate logger", "excluded Social Auth logger"}
        & breadcrumb_messages
    )
    assert (
        "incoming-form-value" in str(reports[0].get("request", {}).get("data"))
    ) is (mode == "pii")
    payload = b"".join(env.serialize() for env in envelopes)
    for secret in (
        INVITATION_TOKEN,
        FORM_SECRET,
        AUTHORIZATION_SECRET,
        "callback-error-secret",
        "callback-span-secret",
    ):
        assert secret.encode() not in payload
    if mode != "pii":
        assert CLIENT_IP.encode() not in payload


if __name__ == "__main__":
    check_startup(sys.argv[1])
