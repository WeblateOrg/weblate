# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Never

import httpx2
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy

from .errors import report_error
from .requests import JSON_RESPONSE_ERRORS, fetch_url

FINGERPRINT = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAASw"
ERR_UNCONFIGURED = "ZAMMAD_URL is not configured!"
ERR_TEMPORARY = gettext_lazy("Customer care is currently unavailable.")


class ZammadError(Exception):
    pass


def _raise_zammad_error(
    cause: str,
    *,
    error: BaseException | None = None,
    extra_log: str | None = None,
) -> Never:
    report_error(
        cause,
        exception=error,
        extra_log=extra_log,
        message=error is None,
    )
    raise ZammadError(ERR_TEMPORARY) from error


def _get_zammad_error_details(response: httpx2.Response) -> str | None:
    try:
        data = response.json()
    except JSON_RESPONSE_ERRORS:
        return None
    if isinstance(data, dict) and "errors" in data:
        return f"Zammad errors: {data['errors']!r}"
    return None


def process_zammad_response(
    response: httpx2.Response, *, context: str = "Zammad"
) -> dict[str, object]:
    try:
        response.raise_for_status()
    except httpx2.HTTPError as error:
        _raise_zammad_error(
            f"{context} response status",
            error=error,
            extra_log=_get_zammad_error_details(response),
        )

    try:
        data = response.json()
    except JSON_RESPONSE_ERRORS as error:
        _raise_zammad_error(f"{context} JSON response", error=error)

    if not isinstance(data, dict):
        _raise_zammad_error(
            f"{context} response schema",
            extra_log=f"Expected an object, got {type(data).__name__}",
        )

    if "errors" in data:
        _raise_zammad_error(
            f"{context} API error",
            extra_log=f"Zammad errors: {data['errors']!r}",
        )

    return data


def _fetch_zammad_response(
    url: str, *, data: dict[str, str], context: str
) -> dict[str, object]:
    try:
        response = fetch_url(
            "POST",
            url,
            data=data,
            raise_for_status=False,
            timeout=10,
        )
    except (OSError, httpx2.HTTPError, httpx2.InvalidURL) as error:
        _raise_zammad_error(f"{context} request", error=error)
    return process_zammad_response(response, context=context)


def _get_zammad_configuration(data: dict[str, object]) -> tuple[str, str]:
    enabled = data.get("enabled")
    if enabled is False:
        _raise_zammad_error("Zammad form is disabled")
    if enabled is not True:
        _raise_zammad_error("Zammad form configuration schema")

    endpoint = data.get("endpoint")
    token = data.get("token")
    if (
        not isinstance(endpoint, str)
        or not endpoint
        or not isinstance(token, str)
        or not token
    ):
        _raise_zammad_error("Zammad form configuration schema")
    return endpoint, token


def _get_zammad_ticket(data: dict[str, object]) -> tuple[str, str]:
    ticket = data.get("ticket")
    if not isinstance(ticket, dict):
        _raise_zammad_error("Zammad ticket response schema")

    ticket_id = ticket.get("id")
    ticket_number = ticket.get("number")
    if (
        not isinstance(ticket_id, str | int)
        or isinstance(ticket_id, bool)
        or not str(ticket_id)
        or not isinstance(ticket_number, str | int)
        or isinstance(ticket_number, bool)
        or not str(ticket_number)
    ):
        _raise_zammad_error("Zammad ticket response schema")
    return str(ticket_id), str(ticket_number)


def submit_zammad_ticket(
    *, title: str, body: str, name: str, email: str, zammad_url: str | None = None
) -> tuple[str, str]:
    if zammad_url is None:
        zammad_url = settings.ZAMMAD_URL
    if not zammad_url:
        raise ImproperlyConfigured(ERR_UNCONFIGURED)

    config_url = f"{zammad_url}/api/v1/form_config"

    data = _fetch_zammad_response(
        config_url,
        data={"fingerprint": FINGERPRINT, "test": "true"},
        context="Zammad form configuration",
    )
    endpoint, token = _get_zammad_configuration(data)

    data = _fetch_zammad_response(
        endpoint,
        data={
            "fingerprint": FINGERPRINT,
            "test": "true",
            "token": token,
            "title": title,
            "name": name,
            "body": body,
            "email": email,
        },
        context="Zammad ticket submission",
    )
    ticket_id, ticket_number = _get_zammad_ticket(data)

    return (
        f"{zammad_url}/#ticket/zoom/{ticket_id}",
        ticket_number,
    )
