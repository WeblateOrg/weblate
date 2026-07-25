# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import httpx2
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .errors import report_error
from .requests import JSON_RESPONSE_ERRORS, fetch_url

FINGERPRINT = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAASw"
ERR_UNCONFIGURED = "ZAMMAD_URL is not configured!"
ERR_TEMPORARY = "Customer care is currently unavailable."


class ZammadError(Exception):
    pass


def process_zammad_response(response: httpx2.Response) -> dict:
    try:
        data = response.json()
    except JSON_RESPONSE_ERRORS as error:
        report_error("Zammad JSON response")
        raise ZammadError(ERR_TEMPORARY) from error

    if "errors" in data:
        raise ZammadError(str(data["errors"]))

    try:
        response.raise_for_status()
    except httpx2.HTTPError as error:
        report_error("Zammad response status")
        raise ZammadError(ERR_TEMPORARY) from error

    return data


def submit_zammad_ticket(
    *, title: str, body: str, name: str, email: str, zammad_url: str | None = None
) -> tuple[str, str]:
    if zammad_url is None:
        zammad_url = settings.ZAMMAD_URL
    if not zammad_url:
        raise ImproperlyConfigured(ERR_UNCONFIGURED)

    config_url = f"{zammad_url}/api/v1/form_config"

    response = fetch_url(
        "POST", config_url, data={"fingerprint": FINGERPRINT, "test": "true"}
    )
    data = process_zammad_response(response)

    if not data.get("enabled"):
        raise ZammadError(ERR_TEMPORARY)

    response = fetch_url(
        "POST",
        data["endpoint"],
        data={
            "fingerprint": FINGERPRINT,
            "test": "true",
            "token": data["token"],
            "title": title,
            "name": name,
            "body": body,
            "email": email,
        },
        timeout=10,
    )
    data = process_zammad_response(response)

    return (
        f"{zammad_url}/#ticket/zoom/{data['ticket']['id']}",
        str(data["ticket"]["number"]),
    )
