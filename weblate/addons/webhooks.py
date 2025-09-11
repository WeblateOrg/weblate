# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import jsonschema.exceptions
import requests
from django.template.loader import render_to_string
from django.utils import timezone as dj_timezone
from django.utils.translation import gettext_lazy
from drf_spectacular.utils import OpenApiResponse, OpenApiWebhook, extend_schema
from standardwebhooks.webhooks import Webhook
from weblate_schemas import load_schema, validate_schema

from weblate.addons.base import ChangeBaseAddon
from weblate.addons.forms import BaseWebhooksAddonForm, WebhooksAddonForm
from weblate.trans.util import split_plural
from weblate.utils.requests import request
from weblate.utils.site import get_site_url
from weblate.utils.views import key_name

if TYPE_CHECKING:
    from weblate.addons.models import AddonActivityLog
    from weblate.trans.models import Change


class MessageNotDeliveredError(Exception):
    """Exception raised when a message could not be delivered."""


class JSONWebhookBaseAddon(ChangeBaseAddon):
    icon = "webhook.svg"

    def build_webhook_payload(self, change: Change) -> dict[str, int | str | list]:
        raise NotImplementedError

    def build_headers(
        self, change: Change, payload: dict[str, int | str | list]
    ) -> dict[str, str]:
        return {}

    def render_activity_log(self, activity: AddonActivityLog) -> str:
        return render_to_string(
            "addons/webhook_log.html",
            {"activity": activity, "details": activity.details["result"]},
        )

    def send_message(
        self, change: Change, headers: dict, payload: dict[str, int | str | list[str]]
    ) -> requests.Response:
        try:
            return request(
                method="post",
                url=self.instance.configuration["webhook_url"],
                json=payload,
                headers=headers,
                timeout=15,
                raise_for_status=False,
            )
        except requests.exceptions.ConnectionError as error:
            raise MessageNotDeliveredError from error

    def change_event(self, change: Change, **kwargs) -> dict | None:
        """Deliver notification message."""
        config = self.instance.configuration
        events = {int(event) for event in config["events"]}
        if change.action in events:
            payload = self.build_webhook_payload(change)
            headers = self.build_headers(change, payload)
            response = self.send_message(change, headers, payload)

            return {
                "request": {"headers": headers, "payload": payload},
                "response": {
                    "status_code": response.status_code,
                    "content": response.text,
                    "headers": dict(response.headers),
                },
            }
        return None


class WebhookAddon(JSONWebhookBaseAddon):
    """Class for Webhooks Addon."""

    name = "weblate.webhook.webhook"
    verbose = gettext_lazy("Webhook")
    description = gettext_lazy(
        "Sends notifications to external services based on selected events, following the Standard Webhooks specification."
    )

    settings_form = WebhooksAddonForm

    def build_webhook_payload(self, change: Change) -> dict[str, int | str | list]:
        """Build a Schema-valid payload from change event."""
        data: dict[str, int | str | list] = {
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
        if change.component and (category := change.component.category):
            categories = []
            while category is not None:
                categories.append(category.slug)
                category = category.category
            if categories:
                data["category"] = categories
        self.validate_payload(data)
        return data

    def build_headers(
        self, change: Change, payload: dict[str, int | str | list]
    ) -> dict[str, str]:
        """Build headers following Standard Webhooks specifications."""
        webhook_id = change.get_uuid().hex
        attempt_time = dj_timezone.now()
        headers: dict[str, str] = {
            "webhook-timestamp": str(attempt_time.timestamp()),
            "webhook-id": webhook_id,
            "webhook-signature": "",
        }
        if secret := self.instance.configuration.get("secret", ""):
            headers["webhook-signature"] = Webhook(secret).sign(
                webhook_id, attempt_time, json.dumps(payload)
            )

        return headers

    def validate_payload(self, payload) -> None:
        try:
            validate_schema(payload, "weblate-messaging.schema.json")
        except (
            jsonschema.exceptions.ValidationError,
            jsonschema.exceptions.SchemaError,
        ) as error:
            raise MessageNotDeliveredError from error


change_event_webhook = OpenApiWebhook(
    name="AddonWebhook",
    decorator=extend_schema(
        summary="A Webhook event for an addon",
        description="Pushes events to a notification URL.",
        tags=["webhooks", "addons"],
        request={"application/json": load_schema("weblate-messaging.schema.json")},
        responses={
            "2XX": OpenApiResponse(),
        },
    ),
)


class SlackWebhookAddon(JSONWebhookBaseAddon):
    name = "weblate.webhook.slack"
    verbose = gettext_lazy("Slack Webhooks")
    description = gettext_lazy(
        "Sends notification to a Slack channel based on selected events."
    )
    icon = "slack.svg"
    settings_form = BaseWebhooksAddonForm

    def build_webhook_payload(self, change: Change) -> dict[str, int | str | list]:
        message_header = ""
        if change.path_object:
            message_header += key_name(change.path_object) + " - "
        message_header += change.get_action_display()
        payload: dict[str, list] = {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": message_header},
                },
            ]
        }

        change_details = change.get_details_display() or "No details"

        payload["blocks"].append(
            {
                "type": "section",
                "text": {"type": "plain_text", "text": change_details},
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View",
                    },
                    "value": "view-change",
                    "url": get_site_url(change.get_absolute_url()),
                },
            }
        )
        return payload
