# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from math import floor
from typing import TYPE_CHECKING

import jsonschema.exceptions
import requests
from django.utils import timezone as dj_timezone
from django.utils.translation import gettext_lazy
from drf_spectacular.utils import OpenApiResponse, OpenApiWebhook, extend_schema
from weblate_schemas import load_schema, validate_schema

from weblate.addons.base import ChangeBaseAddon
from weblate.addons.forms import WebhooksAddonForm
from weblate.trans.util import split_plural
from weblate.utils.requests import request

if TYPE_CHECKING:
    from weblate.trans.models import Change


def hmac_data(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


class WebhookVerificationError(Exception):
    """Exception raised when the payload cannot be validated."""


class MessageNotDeliveredError(Exception):
    """Exception raised when a message could not be delivered."""


class WebhookAddon(ChangeBaseAddon):
    """Class for Webhooks Addon."""

    name = "weblate.webhook.webhook"
    verbose = gettext_lazy("Webhook")
    description = gettext_lazy(
        "Sends notification to external service based on selected events."
    )

    settings_form = WebhooksAddonForm
    icon = "webhook.svg"

    def change_event(self, change: Change) -> dict | None:
        """Deliver notification message."""
        config = self.instance.configuration
        events = {int(event) for event in config["events"]}
        if change.action in events:
            try:
                payload = self.build_webhook_payload(change)
            except (
                jsonschema.exceptions.ValidationError,
                jsonschema.exceptions.SchemaError,
            ) as error:
                raise MessageNotDeliveredError from error

            headers = self.build_headers(change, payload)

            try:
                response = request(
                    method="post",
                    url=config["webhook_url"],
                    json=payload,
                    headers=self.build_headers(change, payload),
                    timeout=15,
                    raise_for_status=False,
                )
            except requests.exceptions.ConnectionError as error:
                raise MessageNotDeliveredError from error

            return {
                "request": {"headers": headers, "payload": payload},
                "response": {
                    "status_code": response.status_code,
                    "content": response.text,
                    "headers": dict(response.headers),
                },
            }
        return None

    def build_webhook_payload(self, change: Change) -> dict[str, int | str | list[str]]:
        """Build a Schema-valid payload from change event."""
        data: dict[str, int | str | list[str]] = {
            "change_id": change.id,
            "action": change.get_action_display(),
            "timestamp": change.timestamp.isoformat(),
        }
        if change.target:
            data["target"] = split_plural(change.target)
        if change.old:
            data["old"] = split_plural(change.old)
        if change.unit:
            data["source"] = split_plural(change.unit.source)
        if url := change.get_absolute_url():
            data["url"] = url
        if change.author:
            data["author"] = change.author.username
        if change.user:
            data["user"] = change.user.username
        if change.project:
            data["project"] = change.project.slug
        if change.component:
            data["component"] = change.component.slug
        if change.translation:
            data["translation"] = change.translation.language.code

        validate_schema(data, "weblate-messaging.schema.json")
        return data

    def build_headers(
        self, change: Change, payload: dict[str, int | str | list[str]]
    ) -> dict[str, str]:
        """Build headers following Standard Webhooks specifications."""
        wh = StandardWebhooksUtils(self.instance.configuration.get("secret", ""))
        webhook_id = change.get_uuid().hex
        attempt_time = dj_timezone.now()
        return {
            "webhook-timestamp": str(attempt_time.timestamp()),
            "webhook-id": webhook_id,
            "webhook-signature": wh.sign(webhook_id, attempt_time, json.dumps(payload)),
        }


class StandardWebhooksUtils:
    """Class providing utils for Standard Webhooks specification."""

    _SECRET_PREFIX: str = "whsec_"  # noqa: S105
    _whsecret: bytes
    SIG_VERSION: str = "v1"

    def __init__(self, whsecret: str | bytes):
        if isinstance(whsecret, str):
            whsecret = whsecret.removeprefix(self._SECRET_PREFIX)
            self._whsecret = base64.b64decode(whsecret)

        elif isinstance(whsecret, bytes):
            self._whsecret = whsecret

    def verify(self, data: bytes | str, headers: dict[str, str]):
        """
        Verify that the data has not been tempered.

        :param data: The data to verify
        :param headers: The headers to verify

        :raises weblate.addons.webhooks.WebhookVerificationError: If the request
            is not verified

        :return: The data as a JSON object if the request is verified
        """
        data = data if isinstance(data, str) else data.decode()
        headers = {k.lower(): v for (k, v) in headers.items()}
        msg_id = headers.get("webhook-id")
        msg_signature = headers.get("webhook-signature")
        msg_timestamp = headers.get("webhook-timestamp")
        if not (msg_id and msg_timestamp and msg_signature):
            msg = "Missing required headers"
            raise WebhookVerificationError(msg)

        timestamp = self.__verify_timestamp(msg_timestamp)

        expected_sig = base64.b64decode(
            self.sign(msg_id=msg_id, timestamp=timestamp, data=data).split(",")[1]
        )
        passed_sigs = msg_signature.split(" ")
        for versioned_sig in passed_sigs:
            (version, signature) = versioned_sig.split(",")
            if version != self.SIG_VERSION:
                continue
            sig_bytes = base64.b64decode(signature)
            if hmac.compare_digest(expected_sig, sig_bytes):
                return json.loads(data)
        msg = "No matching signature found"
        raise WebhookVerificationError(msg)

    def sign(self, msg_id: str, timestamp: datetime, data: str) -> str:
        """Generate a unique signature for payload."""
        timestamp_str = str(floor(timestamp.replace(tzinfo=UTC).timestamp()))
        to_sign = f"{msg_id}.{timestamp_str}.{data}".encode()
        signature = hmac_data(self._whsecret, to_sign)
        return f"{self.SIG_VERSION},{base64.b64encode(signature).decode('utf-8')}"

    def __verify_timestamp(self, timestamp_header: str) -> datetime:
        """Verify if timestamp from header is valid."""
        webhook_tolerance = timedelta(minutes=5)
        now = datetime.now(tz=UTC)
        try:
            timestamp = datetime.fromtimestamp(float(timestamp_header), tz=UTC)
        except Exception as error:
            msg = "Invalid Signature Headers"
            raise WebhookVerificationError(msg) from error

        if timestamp < (now - webhook_tolerance):
            msg = "Message timestamp too old"
            raise WebhookVerificationError(msg)
        if timestamp > (now + webhook_tolerance):
            msg = "Message timestamp too new"
            raise WebhookVerificationError(msg)
        return timestamp


change_event_webhook = OpenApiWebhook(
    name="AddonWebhook",
    decorator=extend_schema(
        summary="A Webhook event for an addon",
        description="Pushes events to a notification URL. ",
        tags=["webhooks", "addons"],
        request={"application/json": load_schema("weblate-messaging.schema.json")},
        responses={
            "2XX": OpenApiResponse(),
        },
    ),
)
