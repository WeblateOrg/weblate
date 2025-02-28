# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from math import floor

from django.utils import timezone as dj_timezone
from django.utils.translation import gettext_lazy

from weblate.addons.base import ChangeBaseAddon
from weblate.addons.forms import WebhooksAddonForm
from weblate.api.tasks import webhook_delivery_task
from weblate.trans.util import split_plural


def hmac_data(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


class WebhookAddon(ChangeBaseAddon):
    name = "weblate.webhook.webhook"
    # TODO: improve description
    verbose = gettext_lazy("Webhooks")
    description = gettext_lazy("some desc")

    settings_form = WebhooksAddonForm
    icon = "webhook.svg"

    def change_event(self, change) -> None:
        config = self.instance.configuration
        if change.action in config["events"]:
            payload = self.build_webhook_payload(change)
            webhook_delivery_task.delay(
                url=config["webhook_url"],
                headers=self.build_headers(change, payload),
                data=payload,
            )

    def build_webhook_payload(self, change) -> dict:
        from weblate.trans.models import Change

        # reload change with prefetched content
        change = Change.objects.prefetch_for_get().get(pk=change.pk)
        data = {
            "id": change.id,
            "action": change.get_action_display(),
        }
        if url := change.get_absolute_url():
            data["url"] = url
        if change.target:
            data["target"] = split_plural(change.target)
        if change.old:
            data["old"] = split_plural(change.old)
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
        if change.unit:
            data["source"] = split_plural(change.unit.source)
            data["context"] = change.unit.context

        return {
            "type": change.get_type(),
            "timestamp": change.timestamp.isoformat(),
            "data": data,
        }

    def build_headers(self, change, payload: dict) -> dict:
        wh = StandardWebhooksUtils(self.instance.configuration.get("secret", ""))
        webhook_id = change.get_uuid().hex
        attempt_time = dj_timezone.now()
        return {
            "webhook-timestamp": str(attempt_time.timestamp()),
            "webhook-id": webhook_id,
            "webhook-signature": wh.sign(webhook_id, attempt_time, json.dumps(payload)),
        }


class WebhookVerificationError(Exception):
    pass


class StandardWebhooksUtils:
    _SECRET_PREFIX: str = "whsec_"  # noqa: S105
    _whsecret: bytes

    def __init__(self, whsecret: str | bytes):
        if isinstance(whsecret, str):
            whsecret = whsecret.removeprefix(self._SECRET_PREFIX)
            self._whsecret = base64.b64decode(whsecret)

        if isinstance(whsecret, bytes):
            self._whsecret = whsecret

    def verify(self, data: bytes | str, headers: dict[str, str]):
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
            if version != "v1":
                continue
            sig_bytes = base64.b64decode(signature)
            if hmac.compare_digest(expected_sig, sig_bytes):
                return json.loads(data)
        msg = "No matching signature found"
        raise WebhookVerificationError(msg)

    def sign(self, msg_id: str, timestamp: datetime, data: str) -> str:
        timestamp_str = str(floor(timestamp.replace(tzinfo=UTC).timestamp()))
        to_sign = f"{msg_id}.{timestamp_str}.{data}".encode()
        signature = hmac_data(self._whsecret, to_sign)
        return f"v1,{base64.b64encode(signature).decode('utf-8')}"

    def __verify_timestamp(self, timestamp_header: str) -> datetime:
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
